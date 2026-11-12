import unittest
from unittest.mock import patch

import pandas as pd

import main
import p1_monitor


class MeterTests(unittest.TestCase):
    def test_reads_ada_one_kw_and_converts_to_watts(self):
        response = {
            'instantaneous_power_import': '0.183',
            'instantaneous_power_export': '1.234',
        }
        with patch.object(p1_monitor, 'IMPORT_PATH', 'instantaneous_power_import'), \
             patch.object(p1_monitor, 'EXPORT_PATH', 'instantaneous_power_export'), \
             patch.object(p1_monitor, 'P1_SCALE', 1000), \
             patch.object(p1_monitor.requests, 'get') as get:
            get.return_value.json.return_value = response
            self.assertEqual(p1_monitor.read_p1(), (1234.0, 183.0))

    def test_missing_fields_do_not_log_the_response(self):
        with patch.object(p1_monitor.requests, 'get') as get:
            get.return_value.json.return_value = {'error': 'private detail'}
            with self.assertRaisesRegex(ValueError, 'P1 válaszból nem olvasható'):
                p1_monitor.read_p1()

    def test_rejects_nonfinite_power(self):
        with patch.object(p1_monitor, 'IMPORT_PATH', 'instantaneous_power_import'), \
             patch.object(p1_monitor, 'EXPORT_PATH', 'instantaneous_power_export'), \
             patch.object(p1_monitor.requests, 'get') as get:
            get.return_value.json.return_value = {
                'instantaneous_power_import': '0',
                'instantaneous_power_export': 'nan',
            }
            with self.assertRaisesRegex(ValueError, 'érvényes, nem negatív'):
                p1_monitor.read_p1()


class CurrentPriceTests(unittest.TestCase):
    def setUp(self):
        p1_monitor._cache.update(slot=None, prices=None)

    def test_selects_current_quarter_and_refreshes_next_quarter(self):
        start = pd.Timestamp('2026-11-12 10:00', tz='Europe/Budapest')
        prices = pd.Series([100.0, 150.0], index=pd.date_range(start, periods=2, freq='15min'))
        with patch.object(p1_monitor, 'EntsoePandasClient') as client:
            client.return_value.query_day_ahead_prices.return_value = prices
            self.assertEqual(p1_monitor.current_price_eur_kwh(start + pd.Timedelta(minutes=14)), 0.1)
            self.assertEqual(p1_monitor.current_price_eur_kwh(start + pd.Timedelta(minutes=15)), 0.15)
            self.assertEqual(client.return_value.query_day_ahead_prices.call_count, 2)

    def test_missing_quarter_does_not_use_previous_price_and_retries(self):
        start = pd.Timestamp('2026-11-12 10:00', tz='Europe/Budapest')
        prices = pd.Series([100.0], index=pd.DatetimeIndex([start]))
        with patch.object(p1_monitor, 'EntsoePandasClient') as client:
            client.return_value.query_day_ahead_prices.return_value = prices
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'Nincs egyértelmű ár'):
                    p1_monitor.current_price_eur_kwh(start + pd.Timedelta(minutes=15))
            self.assertEqual(client.return_value.query_day_ahead_prices.call_count, 2)

    def test_daylight_saving_changes_and_repeated_quarter(self):
        for utc_time, duration in [
            ('2026-03-29 01:15Z', 23),
            ('2026-10-25 00:15Z', 25),
            ('2026-10-25 01:15Z', 25),
        ]:
            with self.subTest(utc_time=utc_time):
                p1_monitor._cache.update(slot=None, prices=None)
                now = pd.Timestamp(utc_time).tz_convert('Europe/Budapest')
                prices = pd.Series([123.0], index=pd.DatetimeIndex([now]))
                with patch.object(p1_monitor, 'EntsoePandasClient') as client:
                    query = client.return_value.query_day_ahead_prices
                    query.return_value = prices
                    self.assertEqual(p1_monitor.current_price_eur_kwh(now), 0.123)
                    start = query.call_args.kwargs['start']
                    end = query.call_args.kwargs['end']
                    self.assertEqual((end - start).total_seconds() / 3600, duration)
                    self.assertEqual(end.hour, 0)


class AlertTests(unittest.TestCase):
    def test_test_mode_sends_email_without_pushover(self):
        with patch.object(main, 'EMAIL_SENDER', 'sender@example.com'), \
             patch.object(main, 'EMAIL_PASSWORD', 'password'), \
             patch.object(main, 'EMAIL_TARGET', 'recipient@example.com'), \
             patch.object(main.smtplib, 'SMTP_SSL') as smtp, \
             patch.object(p1_monitor, 'MAX_PRICE_EUR_MWH', 200), \
             patch.object(p1_monitor, 'current_price_eur_kwh', return_value=0.12345), \
             patch.object(p1_monitor, 'read_p1', side_effect=AssertionError('meter accessed')):
            p1_monitor.main(test_once=True)
            server = smtp.return_value.__enter__.return_value
            server.login.assert_called_once_with('sender@example.com', 'password')
            message = server.send_message.call_args.args[0]
            self.assertEqual(message['To'], 'recipient@example.com')
            self.assertIn('123.45 €/MWh', message.get_content())
            self.assertIn('0.000 kW', message.get_content())

    def test_normal_thresholds_are_strict(self):
        for price, export, expected in [
            (0.199, 1, True),
            (0.199, 0, False),
            (0.200, 1, False),
            (0.201, 1, False),
        ]:
            with self.subTest(price=price, export=export), \
                 patch.object(p1_monitor, 'MAX_PRICE_EUR_MWH', 200), \
                 patch.object(p1_monitor, 'EXPORT_MIN_W', 0), \
                 patch.object(p1_monitor, 'current_price_eur_kwh', return_value=price), \
                 patch.object(p1_monitor, 'read_p1', return_value=(export, 0)), \
                 patch.object(p1_monitor, 'send_alert') as send, \
                 patch.object(p1_monitor.time, 'sleep', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    p1_monitor.main()
                self.assertEqual(send.called, expected)

    def test_missing_email_configuration_is_an_error(self):
        with patch.object(main, 'EMAIL_SENDER', ''), \
             patch.object(main.smtplib, 'SMTP_SSL') as smtp:
            with self.assertRaisesRegex(RuntimeError, 'E-mail nincs konfigurálva'):
                main.send_alert('subject', 'body')
            smtp.assert_not_called()

    def test_email_failure_is_reported(self):
        with patch.object(main, 'EMAIL_SENDER', 'sender@example.com'), \
             patch.object(main, 'EMAIL_PASSWORD', 'password'), \
             patch.object(main, 'EMAIL_TARGET', 'recipient@example.com'), \
             patch.object(main.smtplib, 'SMTP_SSL', side_effect=OSError('connection failed')):
            with self.assertRaisesRegex(RuntimeError, 'E-mail küldési hiba'):
                main.send_alert('subject', 'body')


if __name__ == '__main__':
    unittest.main()
