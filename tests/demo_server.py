"""Offline demo of the Company Brain for screenshots: mock engine, mocked IMAP mailbox, made-up company files in a temp folder.
Usage: python tests/demo_server.py <port> <home-dir>   (nothing real is connected: no network, no model calls, no real mail)"""
import os, sys, zipfile
port, home = sys.argv[1], os.path.abspath(sys.argv[2]); os.makedirs(home, exist_ok=True)
os.environ.update(PORT=port, EMBER_HOME=home, LLM_MOCK="1", EMBER_SECRETS_DIR=os.path.join(home, "secrets"), EMBER_NO_KEYRING="1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [ROOT, os.path.join(ROOT, "tests")]
import brain, fake_imap, server
from test_brain import make_docx, make_xlsx
brain.ITER = 20000; fake_imap.install()  # every IMAP connection in this process is the mock
docs = os.path.join(home, "Company Docs"); os.makedirs(docs, exist_ok=True)
make_docx(os.path.join(docs, "Supplier agreement.docx"), ["Supplier agreement with BeanCo", "Green coffee is fixed at $11.40 per kg until 31 March.", "Payment terms are net 30 days.", "Price changes need 60 days written notice."])
make_xlsx(os.path.join(docs, "price_review.xlsx"), "Prices", [["Item", "Price", "Cost"], ["Cold brew", 5, 1.2], ["Espresso", 3, 0.6], ["Oat latte", 4.5, 1.1]])
open(os.path.join(docs, "refund_policy.md"), "w").write("# Refund policy\n\nRefunds are given within 7 days with a receipt.\nCold brew bottles are not refundable once opened.\n")
open(os.path.join(docs, "sales_oct.csv"), "w").write("week,cold_brew_units,espresso_units\n1,310,880\n2,295,860\n3,240,870\n4,236,850\n")
open(os.path.join(docs, ".private_notes.txt"), "w").write("hidden: never indexed\n"); open(os.path.join(docs, "passwords.txt"), "w").write("never indexed\n")
open(os.path.join(home, "report.py"), "w").write("print('monthly report')\n")
h, pt = "127.0.0.1", int(port); print("http://%s:%d demo (mock engine, mock IMAP, home=%s)" % (h, pt, home), flush=True)
from functools import partial; from http.server import ThreadingHTTPServer
ThreadingHTTPServer((h, pt), partial(server.H, directory=server.PUB)).serve_forever()
