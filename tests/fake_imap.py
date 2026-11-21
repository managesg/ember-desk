"""A mocked IMAP4_SSL for tests and screenshots. Records every call so tests can prove what the app did (and did not) do.
No network, no real mailbox. Addresses use example.com."""
import imaplib, time
from email.message import EmailMessage

def _mail(frm, to, subject, body, date):
    m = EmailMessage(); m["From"], m["To"], m["Subject"], m["Date"] = frm, to, subject, date; m.set_content(body); return m.as_bytes()
MAILBOX = [
    _mail("Dana Reyes <supplier@beanco.example>", "owner@example.com", "Invoice 4471 due Friday", "Hi,\nInvoice 4471 for $812 is due Friday.\nPlease confirm the new bean price of $11.40 per kg.\nCall me on +44 20 7946 0958 if anything is unclear.", "Mon, 16 Nov 2026 09:12:00 +0000"),
    _mail("Landlord <landlord@property.example>", "owner@example.com", "Rent increase notice", "Rent rises 6 percent from January. Please reply by the end of the month.", "Tue, 17 Nov 2026 14:30:00 +0000"),
    _mail("A customer <fan@mail.example>", "owner@example.com", "Why is cold brew $5 now?", "I loved the old price. Is the cold brew staying at $5?", "Wed, 18 Nov 2026 08:05:00 +0000"),
]
class FakeIMAP:
    calls = []; password = None; messages = MAILBOX
    def __init__(self, host, port=993, timeout=None): FakeIMAP.calls.append(("connect", host, port))
    def login(self, user, pw):
        FakeIMAP.calls.append(("login", user))  # never record the password
        if FakeIMAP.password is not None and pw != FakeIMAP.password: raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
        return "OK", [b"logged in"]
    def list(self): FakeIMAP.calls.append(("list",)); return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Drafts) "/" "[Gmail]/Drafts"', b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']
    def select(self, mailbox="INBOX", readonly=False): FakeIMAP.calls.append(("select", mailbox, readonly)); return "OK", [b"%d" % len(self.messages)]
    def search(self, charset, *criteria): FakeIMAP.calls.append(("search",) + criteria); return "OK", [b" ".join(b"%d" % (i + 1) for i in range(len(self.messages)))]
    def fetch(self, i, spec): FakeIMAP.calls.append(("fetch", spec)); raw = self.messages[int(i) - 1]; return "OK", [(b"%s (BODY[] {%d}" % (i, len(raw)), raw), b")"]
    def append(self, mailbox, flags, date_time, message): FakeIMAP.calls.append(("append", mailbox, flags, message)); return "OK", [b"appended"]
    def logout(self): FakeIMAP.calls.append(("logout",)); return "BYE", [b"bye"]
def install(password=None):
    FakeIMAP.calls = []; FakeIMAP.password = password; real = imaplib.IMAP4_SSL; imaplib.IMAP4_SSL = FakeIMAP; return real
def uninstall(real): imaplib.IMAP4_SSL = real
