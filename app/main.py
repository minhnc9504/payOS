from fastapi import FastAPI, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import time
import os
from payos.types import CreatePaymentLinkRequest
from app.database import engine, Base, get_db
from app.models import User, Order
from app.auth import get_password_hash, verify_password, create_access_token, get_current_admin
from app.payos_config import payos_client 

# --- LIFESPAN: Chạy khi khởi động Server ---
# --- LIFESPAN: Chạy khi khởi động Server ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tạo các bảng trong Database (nếu chưa có)
    Base.metadata.create_all(bind=engine)
    
    db = next(get_db())
    admin_user = db.query(User).filter(User.username == "admin").first()
    
    # Lấy mật khẩu từ file .env
    admin_pass = os.getenv("ADMIN_PASSWORD", "123456") 
    
    if not admin_user:
        # Nếu chưa có tài khoản admin -> Tạo mới
        new_admin = User(username="admin", hashed_password=get_password_hash(admin_pass))
        db.add(new_admin)
        db.commit()
    else:
        # NÂNG CẤP: Nếu đã có tài khoản -> Bắt buộc cập nhật lại mật khẩu theo file .env
        admin_user.hashed_password = get_password_hash(admin_pass)
        db.commit()
    yield

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# --- BỘ ROUTER GIAO DIỆN (UI) ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_submit(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        # Trả về trang login kèm lỗi nếu sai
        return RedirectResponse(url="/login?error=1", status_code=status.HTTP_303_SEE_OTHER)
    
    # Đăng nhập thành công, tạo Token và lưu vào Cookie
    access_token = create_access_token(data={"sub": user.username})
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, tx_status: str = None, db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    # Lấy danh sách đơn hàng từ DB. Nếu có param tx_status thì filter theo trạng thái
    query = db.query(Order)
    if tx_status:
        query = query.filter(Order.status == tx_status)
    orders = query.order_by(Order.created_at.desc()).all()
    
    return templates.TemplateResponse("dashboard.html", {"request": request, "orders": orders, "current_filter": tx_status})


# --- BỘ ROUTER CHỨC NĂNG (API) ---
@app.post("/create-payment-link")
async def create_payment_link(
    request: Request,
    amount: int = Form(...), 
    description: str = Form(...), 
    bank_account: str = Form(...), # Nhận thông tin ngân hàng từ form
    db: Session = Depends(get_db), 
    admin: str = Depends(get_current_admin)
):
    # 1. Tạo mã đơn hàng duy nhất bằng timestamp
    order_code = int(time.time())
    YOUR_DOMAIN = os.getenv("DOMAIN", "http://localhost:8000")
    
    # 2. Nối thông tin ngân hàng vào nội dung (giới hạn 25 ký tự theo quy định PayOS)
    full_description = f"{bank_account}: {description}"[:25] 

    # 3. Khởi tạo đối tượng yêu cầu theo chuẩn PayOS Python SDK 1.0.1 [cite: 160]
    payment_request = CreatePaymentLinkRequest(
        order_code=order_code,
        amount=amount,
        description=full_description,
        cancel_url=f"{YOUR_DOMAIN}/",
        return_url=f"{YOUR_DOMAIN}/"
    )

    try:
        # 4. Gọi API của PayOS để tạo link [cite: 32, 160]
        payment_link_data = payos_client.payment_requests.create(payment_request)
        
        # 5. Lưu thông tin đơn hàng VÀ link thanh toán vào Database [cite: 36, 32]
        new_order = Order(
            order_code=order_code, 
            amount=amount, 
            description=full_description, 
            status="PENDING",
            checkout_url=payment_link_data.checkout_url # Cột này dùng để lưu link cũ 
        )
        db.add(new_order)
        db.commit()
        
        # 6. Lấy lại danh sách tất cả đơn hàng để hiển thị ra bảng
        orders = db.query(Order).order_by(Order.created_at.desc()).all()
        
        # 7. Trả về giao diện dashboard kèm biến new_link để hiện khung Copy
        return templates.TemplateResponse("dashboard.html", {
            "request": request, 
            "orders": orders, 
            "new_link": payment_link_data.checkout_url, 
            "order_code": order_code,
            "current_filter": None
        })
        
    except Exception as e:
        # Trả về lỗi nếu quá trình gọi API PayOS thất bại
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/webhook")
async def payos_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    try:
        # Xác thực Webhook chuẩn của Python SDK
        webhook_data = payos_client.webhooks.verify(body)
        
        # Cập nhật DB khi có thanh toán thành công
        order_code = webhook_data.order_code
        order = db.query(Order).filter(Order.order_code == order_code).first()
        if order:
            order.status = "PAID"
            db.commit()
        
        return {"success": True}
    except Exception as e:
        print("Webhook Error:", e)
        return {"success": False}