import os
import html
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, File, UploadFile, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import (
    create_engine, Column, Integer, String, Text,
    inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import secrets


# =========================
# إعداد المتجر وقاعدة البيانات
# =========================

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql://", 1
    )

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./store.db"

engine_options = {}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)
Base = declarative_base()

app = FastAPI(title="أحذية ياسين")

BASE = Path(__file__).resolve().parent
IMG = Path(os.getenv("UPLOAD_DIR", str(BASE / "static")))
IMG.mkdir(parents=True, exist_ok=True)

app.mount(
    "/static",
    StaticFiles(directory=str(IMG)),
    name="static"
)

CATEGORIES = [
    "رياضي",
    "رسمي",
    "كاجوال",
    "سكجر",
    "مستلزمات والعناية بالحذاء"
]

WHATSAPP = "9647774673700"

ADMIN_USER = os.getenv("STORE_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv(
    "STORE_ADMIN_PASSWORD", "ChangeMe123!"
)

security = HTTPBasic()

ALLOWED_IMAGES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp"
}


# =========================
# جدول المنتجات
# =========================

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(150), nullable=False, index=True)
    category = Column(
        String(100), nullable=False, default="كاجوال"
    )
    price = Column(Integer, nullable=False)
    old_price = Column(Integer, nullable=True)
    sizes = Column(String(150), nullable=False, default="متوفر")
    image_url = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)


Base.metadata.create_all(bind=engine)


# إضافة الأعمدة الجديدة إذا كانت قاعدة البيانات قديمة
def migrate_database():
    inspector = inspect(engine)

    if "products" not in inspector.get_table_names():
        return

    columns = {
        col["name"]
        for col in inspector.get_columns("products")
    }

    with engine.begin() as connection:
        if "category" not in columns:
            connection.execute(text(
                "ALTER TABLE products ADD COLUMN "
                "category VARCHAR(100) NOT NULL DEFAULT 'كاجوال'"
            ))

        if "old_price" not in columns:
            connection.execute(text(
                "ALTER TABLE products ADD COLUMN old_price INTEGER"
            ))

        if "description" not in columns:
            connection.execute(text(
                "ALTER TABLE products ADD COLUMN description TEXT"
            ))


migrate_database()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# حماية لوحة الإدارة
# =========================

def require_admin(
    credentials: HTTPBasicCredentials = Depends(security)
):
    user_ok = secrets.compare_digest(
        credentials.username, ADMIN_USER
    )
    pass_ok = secrets.compare_digest(
        credentials.password, ADMIN_PASSWORD
    )

    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="بيانات الدخول غير صحيحة",
            headers={"WWW-Authenticate": "Basic"}
        )

    return credentials.username


# =========================
# أدوات مساعدة
# =========================

def esc(value):
    return html.escape(str(value or ""), quote=True)


def money(value):
    return f"{int(value):,}"


def check_price(value, optional=False):
    if optional and not str(value or "").strip():
        return None

    try:
        number = int(value)
    except (ValueError, TypeError):
        raise HTTPException(400, "اكتب السعر بالأرقام الصحيحة")

    if number < 1 or number > 100_000_000:
        raise HTTPException(400, "السعر غير صحيح")

    return number


async def save_image(photo: UploadFile):
    if not photo or photo.content_type not in ALLOWED_IMAGES:
        raise HTTPException(
            400, "الصورة يجب أن تكون JPG أو PNG أو WEBP"
        )

    data = await photo.read(5 * 1024 * 1024 + 1)

    if not data or len(data) > 5 * 1024 * 1024:
        raise HTTPException(
            400, "الصورة فارغة أو أكبر من 5 ميغابايت"
        )

    filename = uuid.uuid4().hex + ALLOWED_IMAGES[photo.content_type]
    (IMG / filename).write_bytes(data)
    return filename


def category_options(selected=""):
    result = '<option value="">كل الأقسام</option>'

    for category in CATEGORIES:
        chosen = "selected" if category == selected else ""
        result += (
            f'<option value="{esc(category)}" {chosen}>'
            f'{esc(category)}</option>'
        )

    return result


def layout(content):
    return HTMLResponse(f"""
<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>أحذية ياسين</title>
<style>
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    background: #f5f5f5;
    color: #222;
    font-family: Arial, Tahoma, sans-serif;
}}
header {{
    background: #171717;
    color: white;
    text-align: center;
    padding: 22px 10px;
}}
header h1 {{ margin: 0 0 8px; }}
main {{ max-width: 1100px; margin: auto; padding: 14px; }}
.grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
}}
.card, .panel {{
    background: white;
    border-radius: 12px;
    padding: 11px;
    margin-bottom: 12px;
    overflow-wrap: anywhere;
}}
.card img {{
    width: 100%;
    height: 165px;
    object-fit: cover;
    border-radius: 8px;
}}
.card h3 {{ font-size: 15px; }}
.price {{
    color: #16834a;
    font-weight: bold;
    font-size: 18px;
}}
.old {{
    color: #888;
    text-decoration: line-through;
    font-size: 13px;
    margin-left: 5px;
}}
small, .muted {{ color: #666; font-size: 13px; }}
input, select, textarea {{
    width: 100%;
    padding: 12px;
    margin: 5px 0;
    border: 1px solid #ccc;
    border-radius: 8px;
    font-size: 15px;
}}
button, .btn {{
    display: inline-block;
    padding: 10px 13px;
    border: 0;
    border-radius: 8px;
    background: #16834a;
    color: white;
    text-decoration: none;
    cursor: pointer;
    font-size: 14px;
}}
.btn {{ margin: 3px; }}
.order {{
    display: block;
    text-align: center;
    margin-top: 9px;
}}
.stack {{ display: grid; gap: 7px; }}
.danger {{ background: #b42318; }}
.item {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    padding: 10px 0;
    border-bottom: 1px solid #eee;
}}
@media (min-width: 650px) {{
    .grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .card img {{ height: 220px; }}
}}
@media (min-width: 950px) {{
    .grid {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
}}
</style>
</head>
<body>
<header>
<h1>أحذية ياسين 👟</h1>
<p>أحذيتك ومستلزمات العناية بها بمكان واحد</p>
</header>
<main>{content}</main>
</body>
</html>
""")


def product_card(product):
    message = (
        f"السلام عليكم، أريد {product.title}، "
        f"القسم: {product.category}، "
        f"السعر: {money(product.price)} دينار، "
        f"المقاسات: {product.sizes}"
    )

    old_price_html = ""
    saving_html = ""

    if product.old_price and product.old_price > product.price:
        old_price_html = (
            f'<span class="old">{money(product.old_price)} د.ع</span>'
        )
        saving_html = (
            f'<p class="muted">وفّر '
            f'{money(product.old_price - product.price)} د.ع</p>'
        )

    description = ""
    if product.description:
        description = f"<p>{esc(product.description)}</p>"

    return f"""
<article class="card">
<img src="/static/{esc(product.image_url)}"
     alt="{esc(product.title)}" loading="lazy">
<small>{esc(product.category)}</small>
<h3>{esc(product.title)}</h3>
<div class="price">{old_price_html}{money(product.price)} د.ع</div>
{saving_html}
<p class="muted">المقاسات: {esc(product.sizes)}</p>
{description}
<a class="btn order" target="_blank" rel="noopener"
href="https://wa.me/{WHATSAPP}?text={quote(message, safe='')}">
اطلب عبر واتساب
</a>
</article>
"""


# =========================
# واجهة المتجر
# =========================

@app.get("/", response_class=HTMLResponse)
def home(
    q: str = "",
    category: str = "",
    db: Session = Depends(get_db)
):
    q = q.strip()[:80]

    query = db.query(Product)

    if category in CATEGORIES:
        query = query.filter(Product.category == category)

    if q:
        query = query.filter(
            Product.title.contains(q)
            | Product.sizes.contains(q)
            | Product.description.contains(q)
        )

    products = query.order_by(Product.id.desc()).all()

    body = f"""
<form method="get" class="stack">
<input name="q" value="{esc(q)}"
placeholder="ابحث عن حذاء أو مستلزمات أو مقاس">
<select name="category">
{category_options(category if category in CATEGORIES else "")}
</select>
<button type="submit">بحث</button>
</form>
<div>
"""

    for cat in CATEGORIES:
        body += (
            f'<a class="btn" href="/?category={quote(cat, safe="")}">'
            f'{esc(cat)}</a>'
        )

    body += '<a class="btn" href="/">عرض الكل</a></div>'
    body += f"<h3>المنتجات ({len(products)})</h3>"
    body += '<div class="grid">'

    if products:
        body += "".join(product_card(p) for p in products)
    else:
        body += "<p>ماكو منتجات بهذا القسم حالياً.</p>"

    body += '</div>'
    body += '<p><a class="btn" href="/admin">إدارة المتجر</a></p>'

    return layout(body)


# =========================
# لوحة الإدارة
# =========================

@app.get("/admin", response_class=HTMLResponse)
def admin_page(
    _=Depends(require_admin),
    db: Session = Depends(get_db)
):
    products = db.query(Product).order_by(Product.id.desc()).all()

    body = """
<section class="panel">
<h2>إضافة منتج جديد</h2>
<form class="stack" method="post" action="/admin/add"
enctype="multipart/form-data">
<input name="title" placeholder="اسم الحذاء أو المستلزم"
maxlength="150" required>
<select name="category" required>
<option value="">اختار القسم</option>
"""

    for cat in CATEGORIES:
        body += f'<option value="{esc(cat)}">{esc(cat)}</option>'

    body += """
</select>
<input name="price" type="number" min="1"
placeholder="السعر الحالي بالدينار" required>
<input name="old_price" type="number" min="1"
placeholder="السعر القديم (اختياري)">
<input name="sizes" placeholder="المقاسات أو النوع"
maxlength="150" required>
<textarea name="description" placeholder="وصف المنتج (اختياري)"
rows="3"></textarea>
<label>صورة المنتج (حتى 5 ميغابايت)</label>
<input name="photo" type="file"
accept="image/jpeg,image/png,image/webp" required>
<button type="submit">إضافة المنتج</button>
</form>
</section>
<section class="panel"><h2>المنتجات الموجودة</h2>
"""

    if not products:
        body += "<p>ماكو منتجات مضافة بعد.</p>"

    for p in products:
        body += f"""
<div class="item">
<div>
<b>{esc(p.title)}</b><br>
<small>{esc(p.category)} — {money(p.price)} د.ع</small>
</div>
<div>
<a class="btn" href="/admin/edit/{p.id}">تعديل</a>
<form method="post" action="/admin/delete/{p.id}"
style="display:inline"
onsubmit="return confirm('متأكد من حذف المنتج؟')">
<button class="danger">حذف</button>
</form>
</div>
</div>
"""

    body += """
</section>
<a class="btn" href="/">عرض المتجر</a>
"""
    return layout(body)


@app.post("/admin/add")
async def add_product(
    title: str = Form(...),
    category: str = Form(...),
    price: str = Form(...),
    old_price: str = Form(""),
    sizes: str = Form(...),
    description: str = Form(""),
    photo: UploadFile = File(...),
    _=Depends(require_admin),
    db: Session = Depends(get_db)
):
    title, sizes = title.strip(), sizes.strip()
    description = description.strip()

    if not title or len(title) > 150:
        raise HTTPException(400, "تحقق من اسم المنتج")

    if not sizes or len(sizes) > 150:
        raise HTTPException(400, "تحقق من المقاسات أو النوع")

    if category not in CATEGORIES:
        raise HTTPException(400, "القسم غير صحيح")

    current_price = check_price(price)
    previous_price = check_price(old_price, optional=True)

    if previous_price is not None and previous_price <= current_price:
        raise HTTPException(400, "السعر القديم لازم يكون أعلى من الجديد")

    image_name = await save_image(photo)

    product = Product(
        title=title,
        category=category,
        price=current_price,
        old_price=previous_price,
        sizes=sizes,
        description=description or None,
        image_url=image_name
    )

    db.add(product)
    db.commit()

    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/edit/{product_id}", response_class=HTMLResponse)
def edit_page(
    product_id: int,
    _=Depends(require_admin),
    db: Session = Depends(get_db)
):
    p = db.get(Product, product_id)

    if not p:
        raise HTTPException(404, "المنتج غير موجود")

    body = f"""
<section class="panel">
<h2>تعديل المنتج</h2>
<img src="/static/{esc(p.image_url)}"
style="width:150px;max-width:100%">
<form class="stack" method="post"
action="/admin/edit/{p.id}" enctype="multipart/form-data">
<input name="title" value="{esc(p.title)}"
maxlength="150" required>
<select name="category" required>
"""

    for cat in CATEGORIES:
        chosen = "selected" if cat == p.category else ""
        body += (
            f'<option value="{esc(cat)}" {chosen}>'
            f'{esc(cat)}</option>'
        )

    old_price_value = p.old_price if p.old_price is not None else ""

    body += f"""
</select>
<input name="price" type="number" min="1"
value="{p.price}" required>
<input name="old_price" type="number" min="1"
value="{old_price_value}" placeholder="السعر القديم (اختياري)">
<input name="sizes" value="{esc(p.sizes)}"
maxlength="150" required>
<textarea name="description" rows="3"
placeholder="وصف المنتج">{esc(p.description)}</textarea>
<label>اختياري: صورة جديدة</label>
<input name="photo" type="file"
accept="image/jpeg,image/png,image/webp">
<button type="submit">حفظ التعديلات</button>
</form>
<p><a class="btn" href="/admin">رجوع</a></p>
</section>
"""
    return layout(body)


@app.post("/admin/edit/{product_id}")
async def edit_product(
    product_id: int,
    title: str = Form(...),
    category: str = Form(...),
    price: str = Form(...),
    old_price: str = Form(""),
    sizes: str = Form(...),
    description: str = Form(""),
    photo: UploadFile = File(None),
    _=Depends(require_admin),
    db: Session = Depends(get_db)
):
    p = db.get(Product, product_id)

    if not p:
        raise HTTPException(404, "المنتج غير موجود")

    title, sizes = title.strip(), sizes.strip()
    description = description.strip()

    if not title or len(title) > 150:
        raise HTTPException(400, "تحقق من اسم المنتج")

    if not sizes or len(sizes) > 150:
        raise HTTPException(400, "تحقق من المقاسات أو النوع")

    if category not in CATEGORIES:
        raise HTTPException(400, "القسم غير صحيح")

    current_price = check_price(price)
    previous_price = check_price(old_price, optional=True)

    if previous_price is not None and previous_price <= current_price:
        raise HTTPException(400, "السعر القديم لازم يكون أعلى من الجديد")

    p.title = title
    p.category = category
    p.price = current_price
    p.old_price = previous_price
    p.sizes = sizes
    p.description = description or None

    if photo and photo.filename:
        new_image = await save_image(photo)
        old_image_path = IMG / p.image_url
        p.image_url = new_image
        db.commit()

        if old_image_path.exists():
            old_image_path.unlink()
    else:
        db.commit()

    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/delete/{product_id}")
def delete_product(
    product_id: int,
    _=Depends(require_admin),
    db: Session = Depends(get_db)
):
    p = db.get(Product, product_id)

    if p:
        image_path = IMG / p.image_url
        db.delete(p)
        db.commit()

        if image_path.exists():
            image_path.unlink()

    return RedirectResponse("/admin", status_code=303)
