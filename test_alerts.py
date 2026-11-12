import unittest
from unittest.mock import patch

import main
import p1_monitor


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
