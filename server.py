from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
from enum import Enum
import base64
import asyncio
from io import BytesIO

# PDF Generation
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch, mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Rect, String
import urllib.request

# QR Code Generation
import qrcode
from PIL import Image as PILImage

# Email (optional - if configured)
try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection

from pymongo.mongo_client import MongoClient

uri = "mongodb+srv://ombatinyakerumago61_db_user:PaZMXXOzbfb8vUiZ@cluster0.540qxu2.mongodb.net/bfcms_db"

# Create a new client and connect to the server
client = MongoClient(uri)

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb+srv://ombatinyakerumago61_db_user:PaZMXXOzbfb8vUiZ@cluster0.540qxu2.mongodb.net/?retryWrites=true&w=bfcms_db"
# Create a MongoDB client
client = AsyncIOMotorClient(MONGO_URI)

# Select the database you want to use
db = client['bfcms_db']  # <-- Replace with your actual DB name

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'bfcms-secret-key-change-in-production')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Email Configuration
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
if RESEND_AVAILABLE and RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# Choir Logo URL
CHOIR_LOGO_URL = 'https://customer-assets.emergentagent.com/job_choir-manager/artifacts/opi10nbe_logo.png'

## Create the main app
app = FastAPI(title="BFCMS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")
security = HTTPBearer()


# Health check endpoint for Kubernetes deployment
@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes"""
    return {"status": "healthy", "service": "bfcms-api"}

# Enums
class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    CHAIRPERSON = "chairperson"
    SECRETARY = "secretary"
    DISCIPLINARY = "disciplinary"
    TREASURER = "treasurer"
    INVENTORY_OFFICER = "inventory_officer"
    DEPARTMENT_HEAD = "department_head"
    MEMBER = "member"

class MemberStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXITED = "exited"

class Department(str, Enum):
    SOPRANO = "soprano"
    ALTO = "alto"
    TENOR = "tenor"
    BASS = "bass"
    INSTRUMENTS = "instruments"
    MEDIA = "media"

class Office(str, Enum):
    CHAIRPERSON = "chairperson"
    SECRETARY = "secretary"
    DISCIPLINARY = "disciplinary"
    TREASURER = "treasurer"
    INVENTORY = "inventory"
    WELFARE = "welfare"

class CaseStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"

class ItemCondition(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"

class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    CONTRIBUTION = "contribution"

class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    EXCUSED = "excused"

# Models
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole = UserRole.MEMBER

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    full_name: str
    role: UserRole
    department: Optional[str] = None
    created_at: str

class MemberCreate(BaseModel):
    full_name: str
    id_number: str
    phone: str
    email: EmailStr
    department: Department
    date_joined: Optional[str] = None
    photo: Optional[str] = None  # Base64 encoded photo

class MemberUpdate(BaseModel):
    full_name: Optional[str] = None
    id_number: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    department: Optional[Department] = None
    status: Optional[MemberStatus] = None
    photo: Optional[str] = None  # Base64 encoded photo

class MemberResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    membership_number: str
    full_name: str
    id_number: str
    phone: str
    email: str
    department: str
    date_joined: str
    status: str
    created_at: str
    photo: Optional[str] = None

class DisciplinaryCreate(BaseModel):
    member_id: str
    case_description: str

class DisciplinaryUpdate(BaseModel):
    case_description: Optional[str] = None
    committee_decision: Optional[str] = None
    sanctions: Optional[str] = None
    status: Optional[CaseStatus] = None

class DisciplinaryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    member_id: str
    member_name: str
    membership_number: str
    case_description: str
    date_reported: str
    committee_decision: Optional[str] = None
    sanctions: Optional[str] = None
    status: str
    closure_date: Optional[str] = None
    created_by: str

class InventoryCreate(BaseModel):
    name: str
    category: str
    quantity: int
    condition: ItemCondition
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_department: Optional[Department] = None

class InventoryUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[int] = None
    condition: Optional[ItemCondition] = None
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_department: Optional[Department] = None

class InventoryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    item_code: str
    name: str
    category: str
    quantity: int
    condition: str
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_department: Optional[str] = None
    created_at: str

class NoticeCreate(BaseModel):
    title: str
    content: str
    target_department: Optional[str] = None
    expiry_date: Optional[str] = None
    attachment_name: Optional[str] = None
    attachment_data: Optional[str] = None
    attachment_type: Optional[str] = None  # 'image' or 'pdf'

class NoticeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    content: str
    target_department: Optional[str] = None
    expiry_date: Optional[str] = None
    has_attachment: bool
    attachment_name: Optional[str] = None
    attachment_type: Optional[str] = None
    attachment_data: Optional[str] = None  # Include for display
    created_by: str
    created_by_name: str
    created_at: str

class DocumentCreate(BaseModel):
    title: str
    office: Office
    category: str
    file_name: str
    file_data: str

class DocumentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    office: str
    category: str
    file_name: str
    uploaded_by: str
    uploaded_by_name: str
    created_at: str

# Treasury/Finance Models
class ContributionCreate(BaseModel):
    member_id: str
    amount: float
    contribution_type: str
    description: Optional[str] = None
    date: Optional[str] = None

class ContributionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    member_id: str
    member_name: str
    membership_number: str
    amount: float
    contribution_type: str
    description: Optional[str] = None
    date: str
    recorded_by: str
    created_at: str

class TreasuryCreate(BaseModel):
    transaction_type: TransactionType
    amount: float
    description: str
    category: str
    reference: Optional[str] = None

class TreasuryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    transaction_type: str
    amount: float
    description: str
    category: str
    reference: Optional[str] = None
    balance_after: float
    recorded_by: str
    recorded_by_name: str
    created_at: str

# Attendance Models
class AttendanceCreate(BaseModel):
    event_name: str
    event_date: str
    event_type: str  # meeting, rehearsal, performance, etc.

class AttendanceMarkCreate(BaseModel):
    event_id: str
    member_id: str
    status: AttendanceStatus

class AttendanceResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    event_name: str
    event_date: str
    event_type: str
    created_by: str
    created_at: str
    total_present: int = 0
    total_absent: int = 0

class AttendanceRecordResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    event_id: str
    member_id: str
    member_name: str
    membership_number: str
    status: str
    marked_by: str
    created_at: str

class WarningResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    member_id: str
    member_name: str
    membership_number: str
    member_email: str
    consecutive_absences: int
    warning_type: str
    letter_generated: bool
    email_sent: bool
    created_at: str
# Password utilities
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = decode_token(credentials.credentials)
    user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_roles(allowed_roles: List[UserRole]):
    async def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] not in [r.value for r in allowed_roles]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker

# Generate membership number
async def generate_membership_number() -> str:
    year = datetime.now().year
    count = await db.members.count_documents({
        "date_joined": {"$regex": f"^{year}"}
    })
    return f"BFC-{year}-{str(count + 1).zfill(4)}"

# Generate inventory code
async def generate_inventory_code(category: str) -> str:
    prefix = category[:3].upper()
    count = await db.inventory.count_documents({"category": category})
    return f"{prefix}-{str(count + 1).zfill(4)}"

# AUTH ENDPOINTS
@api_router.post("/auth/register", response_model=dict)
async def register(user: UserCreate):
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_doc = {
        "id": str(uuid.uuid4()),
        "email": user.email,
        "password": hash_password(user.password),
        "full_name": user.full_name,
        "role": user.role.value,
        "department": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user_doc)
    
    token = create_token(user_doc["id"], user_doc["role"])
    return {
        "token": token,
        "user": {
            "id": user_doc["id"],
            "email": user_doc["email"],
            "full_name": user_doc["full_name"],
            "role": user_doc["role"]
        }
    }

@api_router.post("/auth/login", response_model=dict)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user["id"], user["role"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "department": user.get("department")
        }
    }

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(**user)

# MEMBERS ENDPOINTS
@api_router.post("/members", response_model=MemberResponse)
async def create_member(
    member: MemberCreate,
    user: dict = Depends(get_current_user)):
    membership_number = await generate_membership_number()
    date_joined = member.date_joined or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    member_doc = {
        "id": str(uuid.uuid4()),
        "membership_number": membership_number,
        "full_name": member.full_name,
        "id_number": member.id_number,
        "phone": member.phone,
        "email": member.email,
        "department": member.department.value,
        "date_joined": date_joined,
        "status": MemberStatus.ACTIVE.value,
        "photo": member.photo,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"]
    }
    await db.members.insert_one(member_doc)
    return MemberResponse(**member_doc)

@api_router.get("/members", response_model=List[MemberResponse])
async def get_members(
    department: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SECRETARY, UserRole.CHAIRPERSON]))
):
    query = {}
    if department:
        query["department"] = department
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"membership_number": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]
    
    members = await db.members.find(query, {"_id": 0}).to_list(1000)
    return [MemberResponse(**m) for m in members]

@api_router.get("/members/{member_id}", response_model=MemberResponse)
async def get_member(member_id: str, user: dict = Depends(get_current_user)):
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return MemberResponse(**member)

@api_router.put("/members/{member_id}", response_model=MemberResponse)
async def update_member(
    member_id: str,
    update: MemberUpdate,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SECRETARY, UserRole.CHAIRPERSON]))
):
    update_data = {k: v.value if isinstance(v, Enum) else v for k, v in update.model_dump(exclude_unset=True).items()}
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided")
    
    result = await db.members.update_one({"id": member_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")
    
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    return MemberResponse(**member)

@api_router.delete("/members/{member_id}")
async def delete_member(
    member_id: str,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN]))
):
    result = await db.members.delete_one({"id": member_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"message": "Member deleted successfully"}

# QR CODE GENERATION
def generate_qr_code(data: str) -> bytes:
    """Generate QR code image as bytes"""
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E3A5F", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer.getvalue()

@api_router.get("/members/{member_id}/qrcode")
async def get_member_qrcode(member_id: str, user: dict = Depends(get_current_user)):
    """Generate QR code for a member"""
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # QR code contains member verification data
    qr_data = f"BFCMS|{member['membership_number']}|{member['full_name']}|{member['department']}"
    qr_bytes = generate_qr_code(qr_data)
    
    return Response(
        content=qr_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=qr_{member['membership_number']}.png"}
    )

# MEMBER ID CARD GENERATION
def generate_member_id_card(member: dict) -> bytes:
    """Generate a professional ID card as PDF"""
    buffer = BytesIO()
    
    # Card size: 3.375 x 2.125 inches (standard ID card) - scaled up for PDF
    card_width = 3.375 * inch * 1.5
    card_height = 2.125 * inch * 1.5
    
    c = canvas.Canvas(buffer, pagesize=(card_width + 40, card_height + 40))
    
    # Card background with rounded corners effect
    c.setFillColor(colors.white)
    c.roundRect(20, 20, card_width, card_height, 10, fill=1, stroke=0)
    
    # Header bar (Deep Blue)
    c.setFillColor(colors.HexColor('#1E3A5F'))
    c.rect(20, card_height - 30, card_width, 50, fill=1, stroke=0)
    
    # Choir name in header
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(card_width/2 + 20, card_height + 5, "THEE BLOSSOM FAMILY CHOIR")
    
    # Subtitle
    c.setFont("Helvetica", 7)
    c.drawCentredString(card_width/2 + 20, card_height - 8, "Member Identification Card")
    
    # Gold accent line
    c.setStrokeColor(colors.HexColor('#F7931E'))
    c.setLineWidth(3)
    c.line(20, card_height - 32, card_width + 20, card_height - 32)
    
    # Try to add logo
    try:
        logo_data = urllib.request.urlopen(CHOIR_LOGO_URL).read()
        logo_buffer = BytesIO(logo_data)
        logo = PILImage.open(logo_buffer)
        logo_io = BytesIO()
        logo.save(logo_io, format='PNG')
        logo_io.seek(0)
        c.drawImage(logo_io, 30, card_height - 95, width=50, height=50, mask='auto')
    except Exception:
        pass
    
    # Member details
    c.setFillColor(colors.HexColor('#1E3A5F'))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(90, card_height - 60, member['full_name'])
    
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor('#F7931E'))
    c.drawString(90, card_height - 75, member['membership_number'])
    
    c.setFillColor(colors.gray)
    c.setFont("Helvetica", 8)
    c.drawString(90, card_height - 90, f"Department: {member['department'].upper()}")
    c.drawString(90, card_height - 102, f"Joined: {member.get('date_joined', 'N/A')}")
    
    # Status badge
    status = member.get('status', 'active')
    if status == 'active':
        c.setFillColor(colors.HexColor('#22C55E'))
    else:
        c.setFillColor(colors.HexColor('#EF4444'))
    c.roundRect(90, card_height - 125, 45, 15, 3, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(112.5, card_height - 121, status.upper())
    
    # QR Code
    qr_data = f"BFCMS|{member['membership_number']}|{member['full_name']}|{member['department']}"
    qr_bytes = generate_qr_code(qr_data)
    qr_buffer = BytesIO(qr_bytes)
    qr_img = Image(qr_buffer, width=55, height=55)
    qr_img.drawOn(c, card_width - 55, 35)
    
    # Footer
    c.setFillColor(colors.HexColor('#1E3A5F'))
    c.rect(20, 20, card_width, 25, fill=1, stroke=0)
    c.setFillColor(colors.HexColor('#F7931E'))
    c.setFont("Helvetica-Oblique", 6)
    c.drawCentredString(card_width/2 + 20, 28, '"Making a joyful noise unto the Lord"')
    
    # Contact info
    c.setFillColor(colors.gray)
    c.setFont("Helvetica", 5)
    c.drawString(30, 50, f"ID: {member.get('id_number', 'N/A')}")
    c.drawString(30, 42, f"Phone: {member.get('phone', 'N/A')}")
    
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

@api_router.get("/members/{member_id}/idcard")
async def get_member_id_card(member_id: str, user: dict = Depends(get_current_user)):
    """Generate and download member ID card as PDF"""
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    pdf_bytes = generate_member_id_card(member)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=idcard_{member['membership_number']}.pdf"}
    )

# DISCIPLINARY ENDPOINTS
@api_router.post("/disciplinary", response_model=DisciplinaryResponse)
async def create_disciplinary_case(
    case: DisciplinaryCreate,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.DISCIPLINARY, UserRole.CHAIRPERSON]))
):
    member = await db.members.find_one({"id": case.member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    case_doc = {
        "id": str(uuid.uuid4()),
        "member_id": case.member_id,
        "member_name": member["full_name"],
        "membership_number": member["membership_number"],
        "case_description": case.case_description,
        "date_reported": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "committee_decision": None,
        "sanctions": None,
        "status": CaseStatus.PENDING.value,
        "closure_date": None,
        "created_by": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.disciplinary.insert_one(case_doc)
    return DisciplinaryResponse(**case_doc)

@api_router.get("/disciplinary", response_model=List[DisciplinaryResponse])
async def get_disciplinary_cases(
    status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    query = {}
    if status:
        query["status"] = status
    cases = await db.disciplinary.find(query, {"_id": 0}).to_list(1000)
    return [DisciplinaryResponse(**c) for c in cases]

@api_router.put("/disciplinary/{case_id}", response_model=DisciplinaryResponse)
async def update_disciplinary_case(
    case_id: str,
    update: DisciplinaryUpdate,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.DISCIPLINARY, UserRole.CHAIRPERSON]))
):
    update_data = {k: v.value if isinstance(v, Enum) else v for k, v in update.model_dump(exclude_unset=True).items()}
    
    if update_data.get("status") == CaseStatus.RESOLVED.value:
        update_data["closure_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    result = await db.disciplinary.update_one({"id": case_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Case not found")
    
    case = await db.disciplinary.find_one({"id": case_id}, {"_id": 0})
    return DisciplinaryResponse(**case)

# INVENTORY ENDPOINTS
@api_router.post("/inventory", response_model=InventoryResponse)
async def create_inventory_item(
    item: InventoryCreate,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.INVENTORY_OFFICER]))
):
    item_code = await generate_inventory_code(item.category)
    
    item_doc = {
        "id": str(uuid.uuid4()),
        "item_code": item_code,
        "name": item.name,
        "category": item.category,
        "quantity": item.quantity,
        "condition": item.condition.value,
        "description": item.description,
        "assigned_to": item.assigned_to,
        "assigned_department": item.assigned_department.value if item.assigned_department else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"]
    }
    await db.inventory.insert_one(item_doc)
    return InventoryResponse(**item_doc)

@api_router.get("/inventory", response_model=List[InventoryResponse])
async def get_inventory(
    category: Optional[str] = None,
    condition: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    query = {}
    if category:
        query["category"] = category
    if condition:
        query["condition"] = condition
    
    items = await db.inventory.find(query, {"_id": 0}).to_list(1000)
    return [InventoryResponse(**i) for i in items]

@api_router.put("/inventory/{item_id}", response_model=InventoryResponse)
async def update_inventory_item(
    item_id: str,
    update: InventoryUpdate,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.INVENTORY_OFFICER]))
):
    update_data = {k: v.value if isinstance(v, Enum) else v for k, v in update.model_dump(exclude_unset=True).items()}
    
    result = await db.inventory.update_one({"id": item_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    
    item = await db.inventory.find_one({"id": item_id}, {"_id": 0})
    return InventoryResponse(**item)

@api_router.delete("/inventory/{item_id}")
async def delete_inventory_item(
    item_id: str,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.INVENTORY_OFFICER]))
):
    result = await db.inventory.delete_one({"id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": "Item deleted successfully"}

# NOTICES ENDPOINTS
@api_router.post("/notices", response_model=NoticeResponse)
async def create_notice(
    notice: NoticeCreate,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SECRETARY, UserRole.CHAIRPERSON, UserRole.DEPARTMENT_HEAD]))
):
    # Handle empty string as None for target_department
    target_dept = notice.target_department if notice.target_department and notice.target_department not in ['', 'all'] else None
    
    # Determine attachment type from filename
    attachment_type = None
    if notice.attachment_name:
        ext = notice.attachment_name.lower().split('.')[-1] if '.' in notice.attachment_name else ''
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            attachment_type = 'image'
        elif ext == 'pdf':
            attachment_type = 'pdf'
        else:
            attachment_type = 'file'
    
    notice_doc = {
        "id": str(uuid.uuid4()),
        "title": notice.title,
        "content": notice.content,
        "target_department": target_dept,
        "expiry_date": notice.expiry_date if notice.expiry_date else None,
        "has_attachment": bool(notice.attachment_data),
        "attachment_name": notice.attachment_name,
        "attachment_type": attachment_type,
        "attachment_data": notice.attachment_data,
        "created_by": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.notices.insert_one(notice_doc)
    
    # Include attachment data in response for images
    response_doc = dict(notice_doc)
    if attachment_type != 'image':
        response_doc.pop('attachment_data', None)
    return NoticeResponse(**response_doc)

@api_router.get("/notices", response_model=List[NoticeResponse])
async def get_notices(
    department: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    query = {}
    if department:
        query["$or"] = [
            {"target_department": department},
            {"target_department": None}
        ]
    
    # Include attachment_data for images to display inline
    notices = await db.notices.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    result = []
    for n in notices:
        # Only include attachment_data for images
        if n.get('attachment_type') != 'image':
            n.pop('attachment_data', None)
        result.append(NoticeResponse(**n))
    return result

@api_router.get("/notices/{notice_id}")
async def get_notice_detail(notice_id: str, user: dict = Depends(get_current_user)):
    """Get single notice with full attachment data"""
    notice = await db.notices.find_one({"id": notice_id}, {"_id": 0})
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")
    return NoticeResponse(**notice)

@api_router.get("/notices/{notice_id}/attachment")
async def get_notice_attachment(notice_id: str, user: dict = Depends(get_current_user)):
    notice = await db.notices.find_one({"id": notice_id}, {"_id": 0})
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")
    if not notice.get("attachment_data"):
        raise HTTPException(status_code=404, detail="No attachment found")
    
    return {
        "file_name": notice["attachment_name"],
        "file_type": notice.get("attachment_type", "file"),
        "file_data": notice["attachment_data"]
    }

@api_router.put("/notices/{notice_id}")
async def update_notice(
    notice_id: str,
    notice: NoticeCreate,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SECRETARY, UserRole.CHAIRPERSON]))
):
    """Update a notice - Super Admin can edit all"""
    existing = await db.notices.find_one({"id": notice_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Notice not found")
    
    target_dept = notice.target_department if notice.target_department and notice.target_department not in ['', 'all'] else None
    
    attachment_type = None
    if notice.attachment_name:
        ext = notice.attachment_name.lower().split('.')[-1] if '.' in notice.attachment_name else ''
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            attachment_type = 'image'
        elif ext == 'pdf':
            attachment_type = 'pdf'
        else:
            attachment_type = 'file'
    
    update_data = {
        "title": notice.title,
        "content": notice.content,
        "target_department": target_dept,
        "expiry_date": notice.expiry_date if notice.expiry_date else None,
        "has_attachment": bool(notice.attachment_data),
        "attachment_name": notice.attachment_name,
        "attachment_type": attachment_type,
        "attachment_data": notice.attachment_data,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.notices.update_one({"id": notice_id}, {"$set": update_data})
    updated = await db.notices.find_one({"id": notice_id}, {"_id": 0})
    return NoticeResponse(**updated)

@api_router.delete("/notices/{notice_id}")
async def delete_notice(
    notice_id: str,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SECRETARY, UserRole.CHAIRPERSON]))
):
    result = await db.notices.delete_one({"id": notice_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notice not found")
    return {"message": "Notice deleted successfully"}

# DOCUMENTS ENDPOINTS
@api_router.post("/documents", response_model=DocumentResponse)
async def create_document(
    doc: DocumentCreate,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SECRETARY, UserRole.CHAIRPERSON]))
):
    doc_record = {
        "id": str(uuid.uuid4()),
        "title": doc.title,
        "office": doc.office.value,
        "category": doc.category,
        "file_name": doc.file_name,
        "file_data": doc.file_data,
        "uploaded_by": user["id"],
        "uploaded_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.documents.insert_one(doc_record)
    
    response_doc = {k: v for k, v in doc_record.items() if k != "file_data"}
    return DocumentResponse(**response_doc)

@api_router.get("/documents", response_model=List[DocumentResponse])
async def get_documents(
    office: Optional[str] = None,
    category: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    query = {}
    if office:
        query["office"] = office
    if category:
        query["category"] = category
    
    docs = await db.documents.find(query, {"_id": 0, "file_data": 0}).sort("created_at", -1).to_list(100)
    return [DocumentResponse(**d) for d in docs]

@api_router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "file_name": doc["file_name"],
        "file_data": doc["file_data"]
    }

@api_router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SECRETARY, UserRole.CHAIRPERSON]))
):
    result = await db.documents.delete_one({"id": doc_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted successfully"}

# USERS MANAGEMENT (Admin only)
@api_router.get("/users", response_model=List[UserResponse])
async def get_users(user: dict = Depends(require_roles([UserRole.SUPER_ADMIN]))):
    users = await db.users.find({}, {"_id": 0, "password": 0}).to_list(1000)
    return [UserResponse(**u) for u in users]

@api_router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: UserRole,
    current_user: dict = Depends(require_roles([UserRole.SUPER_ADMIN]))
):
    result = await db.users.update_one({"id": user_id}, {"$set": {"role": role.value}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Role updated successfully"}

# DASHBOARD STATS
@api_router.get("/dashboard/stats")
async def get_dashboard_stats(user: dict = Depends(get_current_user)):
    total_members = await db.members.count_documents({})
    active_members = await db.members.count_documents({"status": "active"})
    pending_cases = await db.disciplinary.count_documents({"status": "pending"})
    total_inventory = await db.inventory.count_documents({})
    active_notices = await db.notices.count_documents({})
    total_documents = await db.documents.count_documents({})
    total_contributions = await db.contributions.count_documents({})
    pending_warnings = await db.warnings.count_documents({"email_sent": False})
    
    # Get treasury balance
    last_record = await db.treasury.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    treasury_balance = last_record["balance_after"] if last_record else 0.0
    
    # Department counts
    departments = {}
    for dept in Department:
        count = await db.members.count_documents({"department": dept.value, "status": "active"})
        departments[dept.value] = count
    
    return {
        "total_members": total_members,
        "active_members": active_members,
        "pending_cases": pending_cases,
        "total_inventory": total_inventory,
        "active_notices": active_notices,
        "total_documents": total_documents,
        "total_contributions": total_contributions,
        "treasury_balance": treasury_balance,
        "pending_warnings": pending_warnings,
        "departments": departments
    }

# ==================== ADMIN PANEL ENDPOINTS (SUPER ADMIN ONLY) ====================

# Primary admin email for special privileges
PROTECTED_ADMIN_EMAIL = "ombatinyakeruma.go61@gmail.com"

@api_router.get("/admin/system-info")
async def get_system_info(user: dict = Depends(require_roles([UserRole.SUPER_ADMIN]))):
    """Get system information - Super Admin only"""
    total_users = await db.users.count_documents({})
    total_members = await db.members.count_documents({})
    
    # Role distribution
    role_counts = {}
    for role in UserRole:
        count = await db.users.count_documents({"role": role.value})
        role_counts[role.value] = count
    
    return {
        "total_users": total_users,
        "total_members": total_members,
        "role_distribution": role_counts,
        "primary_admin": PROTECTED_ADMIN_EMAIL
    }

@api_router.post("/admin/reset-user-password")
async def admin_reset_password(
    user_email: str,
    new_password: str,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN]))
):
    """Reset any user's password - Super Admin only"""
    # Only primary admin can reset other super admin passwords
    target_user = await db.users.find_one({"email": user_email}, {"_id": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if target_user["role"] == UserRole.SUPER_ADMIN.value and user["email"] != PROTECTED_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Only primary admin can reset super admin passwords")
    
    await db.users.update_one(
        {"email": user_email},
        {"$set": {"password": hash_password(new_password)}}
    )
    return {"message": f"Password reset for {user_email}"}

@api_router.post("/admin/promote-to-admin")
async def promote_to_admin(
    user_email: str,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN]))
):
    """Promote a user to super admin - Only primary admin can do this"""
    if user["email"] != PROTECTED_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Only the primary administrator can promote users to super admin")
    
    target_user = await db.users.find_one({"email": user_email}, {"_id": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await db.users.update_one(
        {"email": user_email},
        {"$set": {"role": UserRole.SUPER_ADMIN.value}}
    )
    return {"message": f"{user_email} promoted to super admin"}

@api_router.delete("/admin/remove-user/{user_id}")
async def remove_user(
    user_id: str,
    user: dict = Depends(require_roles([UserRole.SUPER_ADMIN]))
):
    """Remove a user - Super Admin only, cannot remove primary admin"""
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if target_user["email"] == PROTECTED_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Cannot remove primary administrator")
    
    if target_user["role"] == UserRole.SUPER_ADMIN.value and user["email"] != PROTECTED_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Only primary admin can remove other super admins")
    
    await db.users.delete_one({"id": user_id})
    return {"message": f"User {target_user['email']} removed"}

# ==================== TREASURY ENDPOINTS ====================

@api_router.post("/treasury", response_model=TreasuryResponse)
async def create_treasury_record(
    record: TreasuryCreate,
    user: dict = Depends(get_current_user)
):
    # Calculate new balance
    last_record = await db.treasury.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    current_balance = last_record["balance_after"] if last_record else 0.0
    
    if record.transaction_type == TransactionType.INCOME or record.transaction_type == TransactionType.CONTRIBUTION:
        new_balance = current_balance + record.amount
    else:
        new_balance = current_balance - record.amount
    
    treasury_doc = {
        "id": str(uuid.uuid4()),
        "transaction_type": record.transaction_type.value,
        "amount": record.amount,
        "description": record.description,
        "category": record.category,
        "reference": record.reference,
        "balance_after": new_balance,
        "recorded_by": user["id"],
        "recorded_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.treasury.insert_one(treasury_doc)
    return TreasuryResponse(**treasury_doc)

@api_router.get("/treasury", response_model=List[TreasuryResponse])
async def get_treasury_records(
    transaction_type: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    query = {}
    if transaction_type:
        query["transaction_type"] = transaction_type
    records = await db.treasury.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [TreasuryResponse(**r) for r in records]

@api_router.get("/treasury/summary")
async def get_treasury_summary(user: dict = Depends(get_current_user)):
    # Get current balance
    last_record = await db.treasury.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    current_balance = last_record["balance_after"] if last_record else 0.0
    
    # Calculate totals
    pipeline = [
        {"$group": {
            "_id": "$transaction_type",
            "total": {"$sum": "$amount"}
        }}
    ]
    results = await db.treasury.aggregate(pipeline).to_list(10)
    
    totals = {"income": 0, "expense": 0, "contribution": 0}
    for r in results:
        if r["_id"] in totals:
            totals[r["_id"]] = r["total"]
    
    return {
        "current_balance": current_balance,
        "total_income": totals["income"],
        "total_expenses": totals["expense"],
        "total_contributions": totals["contribution"]
    }

# ==================== CONTRIBUTIONS ENDPOINTS ====================

@api_router.post("/contributions", response_model=ContributionResponse)
async def create_contribution(
    contribution: ContributionCreate,
    user: dict = Depends(get_current_user)
):
    member = await db.members.find_one({"id": contribution.member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    contribution_doc = {
        "id": str(uuid.uuid4()),
        "member_id": contribution.member_id,
        "member_name": member["full_name"],
        "membership_number": member["membership_number"],
        "amount": contribution.amount,
        "contribution_type": contribution.contribution_type,
        "description": contribution.description,
        "date": contribution.date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "recorded_by": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.contributions.insert_one(contribution_doc)
    
    # Also record in treasury
    treasury_doc = {
        "id": str(uuid.uuid4()),
        "transaction_type": "contribution",
        "amount": contribution.amount,
        "description": f"Contribution from {member['full_name']} - {contribution.contribution_type}",
        "category": "contribution",
        "reference": contribution_doc["id"],
        "balance_after": 0,  # Will be calculated
        "recorded_by": user["id"],
        "recorded_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    # Calculate balance
    last_record = await db.treasury.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    current_balance = last_record["balance_after"] if last_record else 0.0
    treasury_doc["balance_after"] = current_balance + contribution.amount
    await db.treasury.insert_one(treasury_doc)
    
    return ContributionResponse(**contribution_doc)

@api_router.get("/contributions", response_model=List[ContributionResponse])
async def get_contributions(
    member_id: Optional[str] = None,
    contribution_type: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    query = {}
    if member_id:
        query["member_id"] = member_id
    if contribution_type:
        query["contribution_type"] = contribution_type
    contributions = await db.contributions.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [ContributionResponse(**c) for c in contributions]

@api_router.get("/contributions/summary")
async def get_contributions_summary(user: dict = Depends(get_current_user)):
    # Total contributions
    pipeline = [
        {"$group": {
            "_id": "$contribution_type",
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }}
    ]
    by_type = await db.contributions.aggregate(pipeline).to_list(20)
    
    # Top contributors
    top_pipeline = [
        {"$group": {
            "_id": "$member_id",
            "member_name": {"$first": "$member_name"},
            "total": {"$sum": "$amount"}
        }},
        {"$sort": {"total": -1}},
        {"$limit": 10}
    ]
    top_contributors = await db.contributions.aggregate(top_pipeline).to_list(10)
    
    total = sum(t["total"] for t in by_type)
    
    return {
        "total_contributions": total,
        "by_type": by_type,
        "top_contributors": top_contributors
    }

# ==================== ATTENDANCE ENDPOINTS ====================

@api_router.post("/attendance/events", response_model=AttendanceResponse)
async def create_attendance_event(
    event: AttendanceCreate,
    user: dict = Depends(get_current_user)
):
    event_doc = {
        "id": str(uuid.uuid4()),
        "event_name": event.event_name,
        "event_date": event.event_date,
        "event_type": event.event_type,
        "created_by": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_present": 0,
        "total_absent": 0
    }
    await db.attendance_events.insert_one(event_doc)
    return AttendanceResponse(**event_doc)

@api_router.get("/attendance/events", response_model=List[AttendanceResponse])
async def get_attendance_events(
    event_type: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    query = {}
    if event_type:
        query["event_type"] = event_type
    events = await db.attendance_events.find(query, {"_id": 0}).sort("event_date", -1).to_list(100)
    return [AttendanceResponse(**e) for e in events]

@api_router.post("/attendance/mark")
async def mark_attendance(
    marks: List[AttendanceMarkCreate],
    user: dict = Depends(get_current_user)
):
    results = []
    for mark in marks:
        member = await db.members.find_one({"id": mark.member_id}, {"_id": 0})
        if not member:
            continue
        
        # Check if already marked
        existing = await db.attendance_records.find_one({
            "event_id": mark.event_id,
            "member_id": mark.member_id
        })
        
        if existing:
            # Update existing record
            await db.attendance_records.update_one(
                {"id": existing["id"]},
                {"$set": {"status": mark.status.value}}
            )
        else:
            # Create new record
            record_doc = {
                "id": str(uuid.uuid4()),
                "event_id": mark.event_id,
                "member_id": mark.member_id,
                "member_name": member["full_name"],
                "membership_number": member["membership_number"],
                "status": mark.status.value,
                "marked_by": user["full_name"],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.attendance_records.insert_one(record_doc)
        
        results.append({"member_id": mark.member_id, "status": mark.status.value})
    
    # Update event totals
    if marks:
        event_id = marks[0].event_id
        present_count = await db.attendance_records.count_documents({"event_id": event_id, "status": "present"})
        absent_count = await db.attendance_records.count_documents({"event_id": event_id, "status": "absent"})
        await db.attendance_events.update_one(
            {"id": event_id},
            {"$set": {"total_present": present_count, "total_absent": absent_count}}
        )
    
    # Check for consecutive absences and generate warnings
    await check_consecutive_absences()
    
    return {"message": "Attendance marked", "results": results}

@api_router.get("/attendance/records/{event_id}", response_model=List[AttendanceRecordResponse])
async def get_attendance_records(event_id: str, user: dict = Depends(get_current_user)):
    records = await db.attendance_records.find({"event_id": event_id}, {"_id": 0}).to_list(500)
    return [AttendanceRecordResponse(**r) for r in records]

@api_router.get("/attendance/member/{member_id}")
async def get_member_attendance(member_id: str, user: dict = Depends(get_current_user)):
    records = await db.attendance_records.find({"member_id": member_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    
    total = len(records)
    present = sum(1 for r in records if r["status"] == "present")
    absent = sum(1 for r in records if r["status"] == "absent")
    excused = sum(1 for r in records if r["status"] == "excused")
    
    return {
        "member_id": member_id,
        "total_events": total,
        "present": present,
        "absent": absent,
        "excused": excused,
        "attendance_rate": (present / total * 100) if total > 0 else 0,
        "records": records
    }

async def check_consecutive_absences():
    """Check for members with 3+ consecutive absences and generate warnings"""
    # Get all active members
    members = await db.members.find({"status": "active"}, {"_id": 0}).to_list(1000)
    
    for member in members:
        # Get last 3 attendance records for this member
        records = await db.attendance_records.find(
            {"member_id": member["id"]},
            {"_id": 0}
        ).sort("created_at", -1).to_list(3)
        
        if len(records) >= 3:
            # Check if all 3 are absences
            consecutive_absences = all(r["status"] == "absent" for r in records[:3])
            
            if consecutive_absences:
                # Check if warning already exists for recent absences
                existing_warning = await db.warnings.find_one({
                    "member_id": member["id"],
                    "warning_type": "attendance",
                    "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()}
                })
                
                if not existing_warning:
                    # Create warning
                    warning_doc = {
                        "id": str(uuid.uuid4()),
                        "member_id": member["id"],
                        "member_name": member["full_name"],
                        "membership_number": member["membership_number"],
                        "member_email": member["email"],
                        "consecutive_absences": 3,
                        "warning_type": "attendance",
                        "letter_generated": False,
                        "email_sent": False,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db.warnings.insert_one(warning_doc)

@api_router.get("/attendance/warnings", response_model=List[WarningResponse])
async def get_attendance_warnings(user: dict = Depends(get_current_user)):
    warnings = await db.warnings.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [WarningResponse(**w) for w in warnings]

# ==================== PDF LETTER GENERATION ====================

def generate_warning_letter_pdf(member_name: str, membership_number: str, consecutive_absences: int, date_str: str) -> bytes:
    """Generate a professional PDF warning letter with letterhead"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1E3A5F'),
        alignment=TA_CENTER,
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#F7931E'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=11,
        leading=16,
        alignment=TA_JUSTIFY,
        spaceAfter=12
    )
    
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontSize=12,
        alignment=TA_LEFT,
        spaceAfter=6
    )
    
    elements = []
    
    # Try to add logo
    try:
        logo_data = urllib.request.urlopen(CHOIR_LOGO_URL).read()
        logo_buffer = BytesIO(logo_data)
        logo = Image(logo_buffer, width=1.2*inch, height=1.2*inch)
        
        # Header table with logo and title
        header_data = [[
            logo,
            [
                Paragraph("<b>THEE BLOSSOM FAMILY CHOIR</b>", title_style),
                Paragraph("Excellence in Harmony • Unity in Worship", subtitle_style),
                Paragraph("P.O. Box 12345, Nairobi, Kenya | Email: info@blossomfamilychoir.org", ParagraphStyle('Contact', fontSize=8, alignment=TA_CENTER))
            ]
        ]]
        header_table = Table(header_data, colWidths=[1.5*inch, 5*inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ]))
        elements.append(header_table)
    except Exception:
        # If logo fails, just add text header
        elements.append(Paragraph("<b>THEE BLOSSOM FAMILY CHOIR</b>", title_style))
        elements.append(Paragraph("Excellence in Harmony • Unity in Worship", subtitle_style))
    
    # Horizontal line
    elements.append(Spacer(1, 10))
    line_table = Table([['']], colWidths=[6.5*inch])
    line_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 2, colors.HexColor('#1E3A5F')),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 20))
    
    # Date
    elements.append(Paragraph(f"Date: {date_str}", header_style))
    elements.append(Spacer(1, 10))
    
    # Reference
    ref_number = f"BFCMS/ATT/WRN/{datetime.now().strftime('%Y%m%d')}/{membership_number[-4:]}"
    elements.append(Paragraph(f"Ref: {ref_number}", header_style))
    elements.append(Spacer(1, 20))
    
    # Recipient
    elements.append(Paragraph(f"<b>{member_name}</b>", header_style))
    elements.append(Paragraph(f"Membership No: {membership_number}", header_style))
    elements.append(Paragraph("Thee Blossom Family Choir", header_style))
    elements.append(Spacer(1, 20))
    
    # Subject
    elements.append(Paragraph("<b><u>RE: ATTENDANCE WARNING NOTICE</u></b>", ParagraphStyle('Subject', fontSize=12, alignment=TA_CENTER, spaceAfter=20)))
    
    # Body
    body_text = f"""
    Dear {member_name},
    
    This letter serves as an official warning regarding your attendance record with Thee Blossom Family Choir.
    
    Our records indicate that you have been absent from <b>{consecutive_absences} consecutive</b> choir meetings/rehearsals without prior notification or approved excuse. As per our choir constitution and attendance policy, regular attendance is essential for maintaining harmony, unity, and the overall success of our choir ministry.
    
    We understand that unforeseen circumstances may arise; however, consistent absence affects not only your own growth and participation but also the collective effort of the entire choir family.
    
    <b>Required Actions:</b>
    <br/>1. Please contact the Secretary or your Department Head within 7 days of receiving this letter to explain your absences.
    <br/>2. If you are facing any challenges preventing your attendance, we encourage you to share them so we can provide appropriate support.
    <br/>3. Failure to respond or continued absence may result in further disciplinary action as outlined in our constitution.
    
    We value your membership and contributions to Thee Blossom Family Choir. We hope to see you at our next gathering and trust that this matter will be resolved amicably.
    
    May God bless you.
    """
    
    elements.append(Paragraph(body_text, body_style))
    elements.append(Spacer(1, 30))
    
    # Signature
    elements.append(Paragraph("Yours in Service,", body_style))
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("_______________________", header_style))
    elements.append(Paragraph("<b>Choir Secretary</b>", header_style))
    elements.append(Paragraph("Thee Blossom Family Choir", header_style))
    
    # Footer line
    elements.append(Spacer(1, 40))
    footer_line = Table([['']], colWidths=[6.5*inch])
    footer_line.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, -1), 1, colors.HexColor('#F7931E')),
    ]))
    elements.append(footer_line)
    elements.append(Paragraph("<i>\"Making a joyful noise unto the Lord\"</i>", ParagraphStyle('Footer', fontSize=9, alignment=TA_CENTER, textColor=colors.gray)))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

@api_router.get("/attendance/warnings/{warning_id}/letter")
async def generate_warning_letter(warning_id: str, user: dict = Depends(get_current_user)):
    warning = await db.warnings.find_one({"id": warning_id}, {"_id": 0})
    if not warning:
        raise HTTPException(status_code=404, detail="Warning not found")
    
    # Generate PDF
    pdf_bytes = generate_warning_letter_pdf(
        warning["member_name"],
        warning["membership_number"],
        warning["consecutive_absences"],
        datetime.now().strftime("%B %d, %Y")
    )
    
    # Update warning record
    await db.warnings.update_one({"id": warning_id}, {"$set": {"letter_generated": True}})
    
    # Return PDF
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=warning_letter_{warning['membership_number']}.pdf"
        }
    )

@api_router.post("/attendance/warnings/{warning_id}/send-email")
async def send_warning_email(warning_id: str, user: dict = Depends(get_current_user)):
    if not RESEND_AVAILABLE or not RESEND_API_KEY:
        raise HTTPException(status_code=400, detail="Email service not configured")
    
    warning = await db.warnings.find_one({"id": warning_id}, {"_id": 0})
    if not warning:
        raise HTTPException(status_code=404, detail="Warning not found")
    
    # Generate email HTML
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background-color: #1E3A5F; padding: 20px; text-align: center;">
            <h1 style="color: #F7931E; margin: 0;">Thee Blossom Family Choir</h1>
            <p style="color: white; margin: 5px 0;">Excellence in Harmony • Unity in Worship</p>
        </div>
        
        <div style="padding: 30px; background-color: #f9f9f9;">
            <h2 style="color: #1E3A5F;">Attendance Warning Notice</h2>
            
            <p>Dear <strong>{warning['member_name']}</strong>,</p>
            
            <p>This email serves as an official warning regarding your attendance record with Thee Blossom Family Choir.</p>
            
            <p>Our records indicate that you have been absent from <strong>{warning['consecutive_absences']} consecutive</strong> choir meetings/rehearsals.</p>
            
            <div style="background-color: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <strong>Required Actions:</strong>
                <ul>
                    <li>Please contact the Secretary within 7 days</li>
                    <li>Explain your absences or challenges</li>
                    <li>Continued absence may result in disciplinary action</li>
                </ul>
            </div>
            
            <p>We value your membership and hope to see you at our next gathering.</p>
            
            <p>May God bless you.</p>
            
            <p><strong>Choir Secretary</strong><br>Thee Blossom Family Choir</p>
        </div>
        
        <div style="background-color: #1E3A5F; padding: 10px; text-align: center;">
            <p style="color: #F7931E; margin: 0; font-style: italic;">"Making a joyful noise unto the Lord"</p>
        </div>
    </div>
    """
    
    try:
        params = {
            "from": SENDER_EMAIL,
            "to": [warning["member_email"]],
            "subject": "Attendance Warning Notice - Thee Blossom Family Choir",
            "html": html_content
        }
        
        email = await asyncio.to_thread(resend.Emails.send, params)
        
        # Update warning record
        await db.warnings.update_one({"id": warning_id}, {"$set": {"email_sent": True}})
        
        return {"message": "Email sent successfully", "email_id": email.get("id")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
from fastapi.middleware.cors import CORSMiddleware 
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://bfcms-frontend-production.up.railway.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include router AFTER middleware
app.include_router(api_router)
# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Primary Admin Configuration - ONLY THIS USER CAN BE INITIAL SUPER ADMIN
PRIMARY_ADMIN_EMAIL = "ombatinyakeruma.go61@gmail.com"
PRIMARY_ADMIN_PASSWORD = "admin123"
PRIMARY_ADMIN_NAME = "Geofrey Ombati"

@app.on_event("startup")
async def startup_db_client():
    """Initialize the primary super admin account on startup"""
    try:
        # Check if primary admin exists
        existing = await db.users.find_one({"email": PRIMARY_ADMIN_EMAIL})
        if existing:
            # Ensure they are super_admin
            if existing.get("role") != UserRole.SUPER_ADMIN.value:
                await db.users.update_one(
                    {"email": PRIMARY_ADMIN_EMAIL},
                    {"$set": {"role": UserRole.SUPER_ADMIN.value}}
                )
                logger.info(f"Updated {PRIMARY_ADMIN_EMAIL} to super_admin role")
        else:
            # Create primary admin
            admin_doc = {
                "id": str(uuid.uuid4()),
                "email": PRIMARY_ADMIN_EMAIL,
                "password": hash_password(PRIMARY_ADMIN_PASSWORD),
                "full_name": PRIMARY_ADMIN_NAME,
                "role": UserRole.SUPER_ADMIN.value,
                "department": None,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.users.insert_one(admin_doc)
            logger.info(f"Created primary super admin: {PRIMARY_ADMIN_EMAIL}")
    except Exception as e:
        logger.error(f"Failed to initialize admin: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

@app.get("/")
def root():
    return {
        "app": "BF CMS Backend",
        "status": "running",
        "docs": "/docs"
    }
