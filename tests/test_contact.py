import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import unquote

from app.api.v1.contact import ContactInquiry, submit_contact_inquiry


class ContactInquiryTests(unittest.TestCase):
    def test_inquiry_is_forwarded_to_configured_recipient(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"success":"true"}'
        inquiry = ContactInquiry(
            name="Taylor Example",
            email="taylor@example.com",
            phone="2055550100",
            message="Please contact me about home care.",
        )

        with patch("app.api.v1.contact.settings.CONTACT_INQUIRY_EMAIL", "angelsathomeal@gmail.com"), patch(
            "app.api.v1.contact.urlopen", return_value=response
        ) as mocked_urlopen:
            result = submit_contact_inquiry(inquiry)

        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertIn("angelsathomeal@gmail.com", unquote(request.full_url))
        self.assertEqual(payload["email"], "taylor@example.com")
        self.assertEqual(payload["phone"], "2055550100")
        self.assertEqual(payload["message"], "Please contact me about home care.")
        self.assertEqual(result, {"success": True, "message": "Message sent."})


if __name__ == "__main__":
    unittest.main()