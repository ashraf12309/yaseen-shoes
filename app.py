from fastapi import FastAPI, Form, File, UploadFile, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from urllib.parse import quote
import sqlite3, secrets, os, uuid, html

app = FastAPI(title="أحذية ياسين")
BASE = Path(__file__).resolve().parent
IMG = BASE / "static"
IMG.mkdir(exist_ok=True)
DB = BASE / "shoes.db"
app.mount("/static", StaticFiles(directory=str(IMG)), name="static")

security = HTTPBasic()
ADMIN = os.getenv("STORE_ADMIN_USER", "admin")
PASSWORD = os.getenv("STORE_ADMIN_PASSWORD", "ChangeMe123!")
CATEGORIES = ["رياضي", "رسمي", "كاجوال", "سكجر"]
TYPES = {"image/jpeg": ".jpg", "image/png": ".png",
         "image/webp": ".webp"}


def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


with connect() as c:
    c.execute("""CREATE TABLE IF NOT EXISTS shoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'كاجوال',
        price INTEGER NOT NULL,
        old_price INTEGER,
        sizes TEXT NOT NULL,
        image TEXT NOT NULL
    )""")
    columns = {r["name"] for r in c.execute("PRAGMA table_info(shoes)")}
    if "category" not in columns:
        c.execute("ALTER TABLE shoes ADD COLUMN category TEXT NOT NULL DEFAULT 'كاجوال'")
    if "old_price" not in columns:
        c.execute("ALTER TABLE shoes ADD COLUMN old_price INTEGER")


def admin(user: HTTPBasicCredentials = Depends(security)):
    ok = secrets.compare_digest(user.username, ADMIN)
    ok &= secrets.compare_digest(user.password, PASSWORD)
    if not ok:
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
    return user.username


def esc(x):
    return html.escape(str(x or ""), quote=True)


def money(x):
    return f"{int(x):,}"


def layout(content):
    return HTMLResponse(f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>أحذية ياسين</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#f4f4f4;color:#222;font-family:Arial,Tahoma}}
header{{background:#171717;color:white;text-align:center;padding:23px 10px}}
main{{max-width:1000px;margin:auto;padding:14px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
.card,.panel{{background:white;border-radius:12px;padding:10px;margin-bottom:12px}}
.card img{{width:100%;height:160px;object-fit:cover;border-radius:8px}}
.card h3{{font-size:15px}}
.price{{color:#16834a;font-weight:bold;font-size:18px}}
.old{{color:#888;text-decoration:line-through;font-size:13px;margin-left:5px}}
small,.sizes{{color:#666;font-size:13px}}
input,select{{width:100%;padding:12px;margin:5px 0;border:1px solid #ccc;border-radius:8px;font-size:15px}}
button,.btn{{display:inline-block;padding:10px 13px;border:0;border-radius:8px;background:#16834a;color:white;text-decoration:none;cursor:pointer;font-size:14px}}
.order{{display:block;text-align:center;margin-top:9px}}
.row{{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}}
.stack{{display:grid;gap:7px}}
.danger{{background:#b42318}}
.item{{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:10px 0;border-bottom:1px solid #eee}}
@media(min-width:650px){{.grid{{grid-template-columns:repeat(3,minmax(0,1fr))}}.card img{{height:220px}}}}
@media(min-width:900px){{.grid{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}
</style></head><body>
<header><h1>أحذية ياسين 👟</h1><p>اختار حذائك واطلب بسهولة</p></header>
<main>{content}</main></body></html>""")


def options(selected=""):
    return "".join(
        f'<option value="{esc(cat)}" {"selected" if cat == selected else ""}>{esc(cat)}</option>'
        for cat in CATEGORIES
    )


def price_check(value, optional=False):
    if optional and not str(value or "").strip():
        return None
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise HTTPException(400, "السعر يجب أن يكون رقماً صحيحاً")
    if n < 1 or n > 100_000_000:
        raise HTTPException(400, "السعر غير صحيح")
    return n


async def save_image(photo):
    if not photo or photo.content_type not in TYPES:
        raise HTTPException(400, "ارفع صورة JPG أو PNG أو WEBP")
    data = await photo.read(5 * 1024 * 1024 + 1)
    if not data or len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "الصورة فارغة أو أكبر من 5 ميغابايت")
    name = uuid.uuid4().hex + TYPES[photo.content_type]
    (IMG / name).write_bytes(data)
    return name


def shoe_card(s):
    msg = (f"السلام عليكم، أريد {s['name']}، القسم {s['category']}، "
           f"السعر {money(s['price'])} دينار، المقاسات {s['sizes']}")
    old = ""
    saving = ""
    if s["old_price"] and s["old_price"] > s["price"]:
        old = f'<span class="old">{money(s["old_price"])} د.ع</span>'
        saving = f'<p class="sizes">وفّر {money(s["old_price"]-s["price"])} د.ع</p>'
    return f"""<article class="card">
<img src="/static/{esc(s['image'])}" alt="{esc(s['name'])}" loading="lazy">
<small>{esc(s['category'])}</small><h3>{esc(s['name'])}</h3>
<div class="price">{old}{money(s['price'])} د.ع</div>{saving}
<p class="sizes">المقاسات: {esc(s['sizes'])}</p>
<a class="btn order" target="_blank" rel="noopener"
href="https://wa.me/9647774673700?text={quote(msg)}">اطلب عبر واتساب</a>
</article>"""


@app.get("/", response_class=HTMLResponse)
def home(q: str = "", category: str = ""):
    if category not in CATEGORIES:
        category = ""
    q = q.strip()[:80]
    sql = "SELECT * FROM shoes WHERE 1=1"
    args = []
    if category:
        sql += " AND category=?"
        args.append(category)
    if q:
        sql += " AND (name LIKE ? OR sizes LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY id DESC"
    with connect() as c:
        shoes = c.execute(sql, args).fetchall()

    body = f"""<form method="get" class="stack">
<input name="q" value="{esc(q)}" placeholder="ابحث عن حذاء أو مقاس">
<select name="category" onchange="this.form.submit()">
<option value="">كل الأقسام</option>{options(category)}</select>
<button>بحث</button></form><div class="row">"""
    for cat in CATEGORIES:
        body += f'<a class="btn" href="/?category={quote(cat)}">{cat}</a>'
    body += '<a class="btn" href="/">عرض الكل</a></div>'
    cards = "".join(shoe_card(s) for s in shoes)
    body += f'<h3>الأحذية المتوفرة ({len(shoes)})</h3>'
    body += f'<div class="grid">{cards or "<p>لا توجد أحذية بهذا القسم حالياً.</p>"}</div>'
    body += '<p><a class="btn" href="/admin">إدارة المتجر</a></p>'
    return layout(body)


@app.get("/admin", response_class=HTMLResponse)
def dashboard(_=Depends(admin)):
    with connect() as c:
        shoes = c.execute("SELECT * FROM shoes ORDER BY id DESC").fetchall()

    body = """<section class="panel"><h2>إضافة حذاء</h2>
<form class="stack" method="post" action="/admin/add" enctype="multipart/form-data">
<input name="name" placeholder="اسم الحذاء" maxlength="100" required>
<select name="category" required><option value="">اختار القسم</option>""" + options() + """
</select>
<input name="price" type="number" min="1" placeholder="السعر الحالي بالدينار" required>
<input name="old_price" type="number" min="1" placeholder="السعر القديم (اختياري)">
<input name="sizes" placeholder="المقاسات، مثال 40، 41، 42" maxlength="100" required>
<label>صورة الحذاء (حتى 5 ميغابايت)</label>
<input name="photo" type="file" accept="image/jpeg,image/png,image/webp" required>
<button>إضافة الحذاء</button></form></section>
<section class="panel"><h2>الأحذية الموجودة</h2>"""
    if not shoes:
        body += "<p>ماكو أحذية مضافة بعد.</p>"
    for s in shoes:
        body += f"""<div class="item"><div><b>{esc(s['name'])}</b><br>
<small>{esc(s['category'])} — {money(s['price'])} د.ع</small></div>
<div><a class="btn" href="/admin/edit/{s['id']}">تعديل</a>
<form method="post" action="/admin/delete/{s['id']}" style="display:inline"
onsubmit="return confirm('متأكد من الحذف؟')">
<button class="danger">حذف</button></form></div></div>"""
    body += '</section><a class="btn" href="/">عرض المتجر</a>'
    return layout(body)


@app.post("/admin/add")
async def add(
    name: str = Form(...), category: str = Form(...),
    price: str = Form(...), old_price: str = Form(""),
    sizes: str = Form(...), photo: UploadFile = File(...),
    _=Depends(admin)
):
    name, sizes = name.strip(), sizes.strip()
    if not name or len(name) > 100 or not sizes or len(sizes) > 100:
        raise HTTPException(400, "تحقق من الاسم والمقاسات")
    if category not in CATEGORIES:
        raise HTTPException(400, "القسم غير صحيح")
    p = price_check(price)
    old = price_check(old_price, True)
    if old is not None and old <= p:
        raise HTTPException(400, "السعر القديم لازم يكون أعلى من الجديد")
    image = await save_image(photo)
    with connect() as c:
        c.execute("""INSERT INTO shoes(name,category,price,old_price,sizes,image)
        VALUES(?,?,?,?,?,?)""", (name, category, p, old, sizes, image))
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/edit/{sid}", response_class=HTMLResponse)
def edit_page(sid: int, _=Depends(admin)):
    with connect() as c:
        s = c.execute("SELECT * FROM shoes WHERE id=?", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "الحذاء غير موجود")
    body = f"""<section class="panel"><h2>تعديل الحذاء</h2>
<img src="/static/{esc(s['image'])}" style="width:140px;max-width:100%">
<form class="stack" method="post" action="/admin/edit/{sid}" enctype="multipart/form-data">
<input name="name" value="{esc(s['name'])}" maxlength="100" required>
<select name="category" required>{options(s['category'])}</select>
<input name="price" type="number" min="1" value="{s['price']}" required>
<input name="old_price" type="number" min="1" value="{esc(s['old_price'])}" placeholder="السعر القديم (اختياري)">
<input name="sizes" value="{esc(s['sizes'])}" maxlength="100" required>
<label>اختياري: صورة جديدة</label>
<input name="photo" type="file" accept="image/jpeg,image/png,image/webp">
<button>حفظ التعديلات</button></form>
<p><a class="btn" href="/admin">رجوع</a></p></section>"""
    return layout(body)


@app.post("/admin/edit/{sid}")
async def edit(
    sid: int, name: str = Form(...), category: str = Form(...),
    price: str = Form(...), old_price: str = Form(""),
    sizes: str = Form(...), photo: UploadFile = File(None),
    _=Depends(admin)
):
    name, sizes = name.strip(), sizes.strip()
    if not name or len(name) > 100 or not sizes or len(sizes) > 100:
        raise HTTPException(400, "تحقق من الاسم والمقاسات")
    if category not in CATEGORIES:
        raise HTTPException(400, "القسم غير صحيح")
    p, old = price_check(price), price_check(old_price, True)
    if old is not None and old <= p:
        raise HTTPException(400, "السعر القديم لازم يكون أعلى من الجديد")

    with connect() as c:
        s = c.execute("SELECT * FROM shoes WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "الحذاء غير موجود")
        image = s["image"]
        if photo and photo.filename:
            new_image = await save_image(photo)
            (IMG / image).unlink(missing_ok=True)
            image = new_image
        c.execute("""UPDATE shoes SET name=?,category=?,price=?,old_price=?,
        sizes=?,image=? WHERE id=?""",
        (name, category, p, old, sizes, image, sid))
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/delete/{sid}")
def delete(sid: int, _=Depends(admin)):
    with connect() as c:
        s = c.execute("SELECT image FROM shoes WHERE id=?", (sid,)).fetchone()
        if s:
            c.execute("DELETE FROM shoes WHERE id=?", (sid,))
            (IMG / s["image"]).unlink(missing_ok=True)
    return RedirectResponse("/admin", status_code=303)