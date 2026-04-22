import os
from payos import PayOS
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("PAYOS_CLIENT_ID")
API_KEY = os.getenv("PAYOS_API_KEY")
CHECKSUM_KEY = os.getenv("PAYOS_CHECKSUM_KEY")

# Khởi tạo đối tượng PayOS
payos_client = PayOS(
    client_id=CLIENT_ID,
    api_key=API_KEY,
    checksum_key=CHECKSUM_KEY
)