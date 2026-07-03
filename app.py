from flask import Flask, render_template_string, request, redirect, url_for, flash, send_from_directory, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import random
import string

# =========================================================
# APP
# =========================================================
app = Flask(__name__)

# Configurazione pronta per online:
# - in locale usa SQLite automaticamente
# - online usa PostgreSQL se la piattaforma imposta DATABASE_URL
#   (Render/Heroku spesso forniscono un URL postgres://: lo convertiamo per SQLAlchemy)
database_url = os.environ.get("DATABASE_URL", "sqlite:///database.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambia-questa-chiave-in-produzione")
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "doc", "docx", "xls", "xlsx", "txt"}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Accedi per continuare"

# =========================================================
# MODELS
# =========================================================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Immobile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codice = db.Column(db.String(100))
    titolo = db.Column(db.String(255))
    descrizione = db.Column(db.Text)
    citta = db.Column(db.String(100))
    indirizzo = db.Column(db.String(255))
    prezzo = db.Column(db.Float)
    metri_quadri = db.Column(db.Integer)
    camere = db.Column(db.Integer)
    bagni = db.Column(db.Integer)
    stato = db.Column(db.String(100))
    clienti = db.relationship("Cliente", backref="immobile", lazy=True)
    foto = db.relationship("FotoImmobile", backref="immobile", lazy=True, cascade="all, delete-orphan")
    allegati = db.relationship("AllegatoImmobile", backref="immobile", lazy=True, cascade="all, delete-orphan")


class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    cognome = db.Column(db.String(100))
    telefono = db.Column(db.String(100))
    email = db.Column(db.String(100))
    note = db.Column(db.Text)
    immobile_id = db.Column(db.Integer, db.ForeignKey("immobile.id"), nullable=True)
    allegati = db.relationship("AllegatoCliente", backref="cliente", lazy=True, cascade="all, delete-orphan")
    pagamenti = db.relationship("PagamentoCliente", backref="cliente", lazy=True, cascade="all, delete-orphan")


class FotoImmobile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    immobile_id = db.Column(db.Integer, db.ForeignKey("immobile.id"))
    filename = db.Column(db.String(255))


class AllegatoImmobile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    immobile_id = db.Column(db.Integer, db.ForeignKey("immobile.id"))
    filename = db.Column(db.String(255))


class AllegatoCliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"))
    filename = db.Column(db.String(255))
    caricato_il = db.Column(db.DateTime, default=datetime.utcnow)


class PagamentoCliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"), nullable=False)
    descrizione = db.Column(db.String(255))
    importo = db.Column(db.Float, default=0)
    data_pagamento = db.Column(db.String(20), nullable=True)
    data_scadenza = db.Column(db.String(20), nullable=True)
    note = db.Column(db.Text)
    creato_il = db.Column(db.DateTime, default=datetime.utcnow)


class Appuntamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titolo = db.Column(db.String(255))
    data = db.Column(db.String(100))
    ora = db.Column(db.String(50))
    luogo = db.Column(db.String(255))
    note = db.Column(db.Text)

# =========================================================
# LOGIN
# =========================================================
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# =========================================================
# UTILS
# =========================================================
def genera_codice():
    return "IMM-" + "".join(random.choice(string.digits) for _ in range(6))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def salva_file(file, prefisso="file"):
    if not file or file.filename == "":
        return None
    if not allowed_file(file.filename):
        return None
    nome_originale = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nome = f"{prefisso}_{timestamp}_{nome_originale}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], nome))
    return nome


def elimina_file_fisico(filename):
    if not filename:
        return
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def euro(valore):
    try:
        return f"€ {valore:,.0f}".replace(",", ".")
    except Exception:
        return "€ 0"


def formato_data(data):
    if not data:
        return "—"
    try:
        return datetime.strptime(data, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return data


def pagamento_scaduto(pagamento):
    if pagamento.data_pagamento or not pagamento.data_scadenza:
        return False
    try:
        return datetime.strptime(pagamento.data_scadenza, "%Y-%m-%d").date() < datetime.today().date()
    except Exception:
        return False


def giorni_alla_scadenza(pagamento):
    if not pagamento.data_scadenza:
        return None
    try:
        scadenza = datetime.strptime(pagamento.data_scadenza, "%Y-%m-%d").date()
        return (scadenza - datetime.today().date()).days
    except Exception:
        return None


def stato_pagamento(pagamento):
    if pagamento.data_pagamento:
        return "pagato", "payment-ok", '<span class="badge text-bg-success">Pagato</span>'
    giorni = giorni_alla_scadenza(pagamento)
    if giorni is None:
        return "senza_scadenza", "", '<span class="badge text-bg-secondary">Senza scadenza</span>'
    if giorni < 0:
        return "scaduto", "payment-overdue", '<span class="badge text-bg-danger">Scaduto / non pagato</span>'
    if giorni <= 15:
        return "in_scadenza", "payment-soon", '<span class="badge text-bg-warning">Manca poco</span>'
    return "ok", "payment-ok", '<span class="badge text-bg-success">Ok</span>'

# =========================================================
# TEMPLATE
# =========================================================
BASE_HTML = """
<!doctype html>
<html lang="it">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Gestionale</title>
    <meta name="theme-color" content="#111827">
    <link rel="manifest" href="/manifest.json">
    <link rel="apple-touch-icon" href="/static-icon.png">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        :root{
            --bg:#eef3fb;
            --panel:#ffffff;
            --dark:#111827;
            --muted:#6b7280;
            --primary:#2563eb;
            --primary-soft:#e8efff;
            --success:#16a34a;
            --warning:#f59e0b;
            --radius:22px;
        }
        body{
            min-height:100vh;
            background:
                radial-gradient(circle at top left, rgba(37,99,235,.18), transparent 35%),
                linear-gradient(135deg, #f8fbff 0%, var(--bg) 100%);
            color:var(--dark);
        }
        .app-shell{display:flex;min-height:100vh;}
        .sidebar{
            width:270px;
            background:rgba(17,24,39,.96);
            color:white;
            padding:26px 20px;
            position:sticky;
            top:0;
            height:100vh;
            box-shadow:8px 0 30px rgba(17,24,39,.16);
        }
        .brand{font-size:22px;font-weight:800;letter-spacing:-.04em;margin-bottom:34px;display:flex;gap:10px;align-items:center;}
        .brand-icon{width:42px;height:42px;border-radius:14px;background:var(--primary);display:grid;place-items:center;}
        .nav-link-custom{
            display:flex;align-items:center;gap:12px;color:#d1d5db;text-decoration:none;
            padding:13px 14px;border-radius:14px;margin-bottom:7px;font-weight:600;
        }
        .nav-link-custom:hover,.nav-link-custom.active{background:rgba(255,255,255,.10);color:white;}
        .main{flex:1;padding:30px;}
        .topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:25px;}
        .page-title{font-weight:850;letter-spacing:-.04em;margin:0;}
        .soft-card{background:rgba(255,255,255,.85);backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,.75);border-radius:var(--radius);box-shadow:0 18px 45px rgba(31,41,55,.08);}
        .metric{padding:24px;position:relative;overflow:hidden;}
        .metric .icon{width:52px;height:52px;border-radius:16px;background:var(--primary-soft);color:var(--primary);display:grid;place-items:center;font-size:24px;margin-bottom:18px;}
        .metric h2{font-size:42px;font-weight:850;margin:0;}
        .metric p{color:var(--muted);margin:0;font-weight:600;}
        .btn-rounded{border-radius:14px;padding:11px 18px;font-weight:700;}
        .table{margin-bottom:0;}
        .table thead th{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);border-bottom:1px solid #e5e7eb;}
        .table tbody tr{cursor:pointer;vertical-align:middle;}
        .table tbody tr:hover{background:#f8fafc;}
        .pill{display:inline-flex;align-items:center;gap:6px;padding:7px 11px;border-radius:999px;background:var(--primary-soft);color:var(--primary);font-size:13px;font-weight:700;}
        .form-control,.form-select{border-radius:14px;padding:12px 14px;border:1px solid #dbe2ef;}
        .form-label{font-weight:750;color:#374151;}
        .detail-hero{padding:30px;}
        .muted{color:var(--muted);}
        .file-tile{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border:1px solid #e5e7eb;border-radius:16px;text-decoration:none;color:var(--dark);background:#fff;margin-bottom:10px;}
        .file-tile:hover{border-color:var(--primary);color:var(--primary);}
        .gallery-img{width:220px;height:150px;object-fit:cover;border-radius:18px;margin:8px;box-shadow:0 12px 25px rgba(15,23,42,.12);}
        .payment-overdue{background:#fee2e2!important;color:#7f1d1d;}
        .payment-overdue td{border-color:#fecaca!important;}
        .payment-soon{background:#fef3c7!important;color:#78350f;}
        .payment-soon td{border-color:#fde68a!important;}
        .payment-ok{background:#dcfce7!important;color:#14532d;}
        .payment-ok td{border-color:#bbf7d0!important;}
        .thumb-admin{width:110px;height:75px;object-fit:cover;border-radius:12px;border:1px solid #e5e7eb;}
        .calendar-wrapper{background:white;border-radius:24px;overflow:hidden;box-shadow:0 18px 45px rgba(31,41,55,.08);}
        .calendar-top{display:flex;justify-content:space-between;align-items:center;padding:24px;border-bottom:1px solid #eef2f7;}
        .calendar-grid{display:flex;overflow:auto;}
        .ore-colonna{width:86px;background:#f8fafc;border-right:1px solid #eef2f7;flex:0 0 auto;}
        .ora-slot{height:78px;border-bottom:1px solid #eef2f7;text-align:center;padding-top:8px;color:#64748b;font-size:13px;}
        .giorni-container{display:grid;grid-template-columns:repeat(7, minmax(170px, 1fr));width:100%;min-width:1190px;}
        .giorno-colonna{border-right:1px solid #eef2f7;position:relative;}
        .giorno-header{height:70px;display:flex;align-items:center;justify-content:center;border-bottom:1px solid #eef2f7;background:white;}
        .giorno-nome{font-weight:800}.giorno-data{font-size:13px;color:#64748b;text-align:center;}
        .giorno-body{position:relative;height:1014px;background-image:linear-gradient(to bottom,#eef2f7 1px,transparent 1px);background-size:100% 78px;}
        .evento{position:absolute;left:8px;width:calc(100% - 16px);min-height:84px;background:linear-gradient(135deg,#2563eb,#1d4ed8);color:white;border-radius:16px;padding:12px;box-shadow:0 12px 25px rgba(37,99,235,.25);}

        .quick-actions{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px;}
        .quick-action{display:inline-flex;align-items:center;gap:10px;padding:12px 16px;border-radius:16px;background:#fff;text-decoration:none;color:#111827;font-weight:800;border:1px solid #e5e7eb;box-shadow:0 10px 24px rgba(31,41,55,.06);}
        .quick-action:hover{transform:translateY(-1px);border-color:var(--primary);color:var(--primary);}
        .empty-state{padding:34px;text-align:center;border:1px dashed #cbd5e1;border-radius:20px;background:#f8fafc;color:#64748b;}
        .section-title{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px;}
        .table-card{overflow:hidden;}
        .status-dot{width:10px;height:10px;border-radius:999px;display:inline-block;background:currentColor;}
        .agenda-payment{background:linear-gradient(135deg,#f97316,#ea580c)!important;box-shadow:0 12px 25px rgba(249,115,22,.25)!important;}
        .agenda-appointment{background:linear-gradient(135deg,#2563eb,#1d4ed8)!important;}
        .agenda-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:18px;}
        .agenda-item{padding:16px;border-radius:18px;background:white;border:1px solid #e5e7eb;box-shadow:0 10px 22px rgba(31,41,55,.05);}
        .agenda-item strong{display:block;margin-bottom:6px;}
        .hint-box{border-radius:18px;background:#eff6ff;border:1px solid #bfdbfe;color:#1e3a8a;padding:14px 16px;font-weight:650;}
        .mobile-header{display:none;}
        .mobile-overlay{display:none;}
        @media(max-width:900px){
            body{background:#f8fafc;}
            .mobile-header{display:flex;position:sticky;top:0;z-index:1040;align-items:center;justify-content:space-between;padding:12px 14px;background:rgba(17,24,39,.96);color:white;box-shadow:0 12px 30px rgba(15,23,42,.18);}
            .mobile-header .brand{margin:0;font-size:18px;}
            .mobile-menu-btn{border:0;background:rgba(255,255,255,.12);color:white;border-radius:14px;width:44px;height:44px;font-size:22px;}
            .app-shell{display:block;min-height:auto;}
            .sidebar{position:fixed;left:-292px;top:0;bottom:0;width:286px;height:100vh;z-index:1050;transition:left .22s ease;overflow-y:auto;}
            .sidebar.open{left:0;}
            .mobile-overlay{display:block;position:fixed;inset:0;background:rgba(15,23,42,.45);z-index:1045;opacity:0;pointer-events:none;transition:opacity .2s ease;}
            .mobile-overlay.show{opacity:1;pointer-events:auto;}
            .main{padding:16px;padding-bottom:32px;}
            .topbar{display:block;margin-bottom:18px;}
            .topbar .d-flex{margin-top:12px;}
            .topbar .btn{margin-top:0;}
            .page-title{font-size:30px;}
            .soft-card{border-radius:18px;}
            .metric{padding:18px;}
            .metric h2{font-size:34px;}
            .quick-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
            .quick-action{justify-content:center;padding:14px 10px;text-align:center;}
            .table-responsive{overflow:visible;}
            table.table thead{display:none;}
            table.table, table.table tbody, table.table tr, table.table td{display:block;width:100%;}
            table.table tr{border:1px solid #e5e7eb;border-radius:18px;margin-bottom:12px;padding:10px;background:white;box-shadow:0 8px 18px rgba(31,41,55,.05);}
            table.table td{border:0!important;padding:7px 8px;}
            table.table td.text-end{text-align:left!important;}
            .gallery-img{width:100%;height:210px;margin:8px 0;}
            .file-tile{align-items:flex-start;word-break:break-word;}
            .calendar-wrapper{box-shadow:none;background:transparent;overflow:visible;}
            .calendar-grid{display:block;overflow:visible;}
            .ore-colonna{display:none;}
            .giorni-container{display:block;min-width:0;width:100%;}
            .giorno-colonna{border:0;margin-bottom:14px;background:white;border-radius:18px;overflow:hidden;box-shadow:0 8px 18px rgba(31,41,55,.05);}
            .giorno-header{height:auto;justify-content:flex-start;padding:14px 16px;background:#f8fafc;}
            .giorno-body{height:auto;min-height:80px;background:none;padding:12px;}
            .evento{position:relative!important;top:auto!important;left:auto!important;width:100%!important;min-height:auto;margin-bottom:10px;}
            .agenda-list{grid-template-columns:1fr;}
        }
        @media(max-width:480px){
            .quick-actions{grid-template-columns:1fr;}
            .btn-rounded{width:100%;}
            .d-flex.gap-2{gap:8px!important;}
            .detail-hero{padding:20px;}
        }
    </style>
</head>
<body>
{% if current_user.is_authenticated %}
<header class="mobile-header">
    <div class="brand"><div class="brand-icon"><i class="bi bi-building"></i></div><span>Gestionale</span></div>
    <button class="mobile-menu-btn" type="button" aria-label="Apri menu" onclick="toggleMobileMenu()"><i class="bi bi-list"></i></button>
</header>
<div class="mobile-overlay" onclick="toggleMobileMenu(false)"></div>
<div class="app-shell">
    <aside class="sidebar" id="appSidebar">
        <div class="brand"><div class="brand-icon"><i class="bi bi-building"></i></div><span>Gestionale</span></div>
        <a class="nav-link-custom" href="/"><i class="bi bi-speedometer2"></i>Dashboard</a>
        <a class="nav-link-custom" href="/immobili"><i class="bi bi-houses"></i>Immobili</a>
        <a class="nav-link-custom" href="/clienti"><i class="bi bi-people"></i>Pazienti / Clienti</a>
        <a class="nav-link-custom" href="/pagamenti"><i class="bi bi-cash-stack"></i>Pagamenti</a>
        <a class="nav-link-custom" href="/agenda"><i class="bi bi-calendar-week"></i>Agenda</a>
        <a class="nav-link-custom" href="/logout"><i class="bi bi-box-arrow-right"></i>Logout</a>
    </aside>
    <main class="main">
{% else %}
<main class="main">
{% endif %}
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}<div class="alert alert-success soft-card border-0">{{ message }}</div>{% endfor %}
            {% endif %}
        {% endwith %}
        {{ content|safe }}
{% if current_user.is_authenticated %}</main></div>{% else %}</main>{% endif %}
<script>
    function toggleMobileMenu(force){
        const sidebar = document.getElementById('appSidebar');
        const overlay = document.querySelector('.mobile-overlay');
        if(!sidebar || !overlay) return;
        const open = typeof force === 'boolean' ? force : !sidebar.classList.contains('open');
        sidebar.classList.toggle('open', open);
        overlay.classList.toggle('show', open);
    }
    document.querySelectorAll('.nav-link-custom').forEach(a => {
        const path = window.location.pathname;
        const href = a.getAttribute('href');
        if (href === '/' ? path === '/' : path.startsWith(href)) a.classList.add('active');
        a.addEventListener('click', () => toggleMobileMenu(false));
    });
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => navigator.serviceWorker.register('/service-worker.js').catch(() => {}));
    }
</script>
</body>
</html>
"""

# =========================================================
# AUTH
# =========================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username", "")).first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Credenziali errate")

    html = """
    <div class="d-flex align-items-center justify-content-center" style="min-height:85vh;">
        <div class="soft-card p-5" style="max-width:460px;width:100%;">
            <div class="text-center mb-4">
                <div class="brand-icon mx-auto mb-3 text-white"><i class="bi bi-shield-lock"></i></div>
                <h1 class="page-title">Bentornato</h1>
                <p class="muted">Accedi al tuo gestionale</p>
            </div>
            <form method="POST">
                <label class="form-label">Username</label>
                <input class="form-control mb-3" name="username" placeholder="admin">
                <label class="form-label">Password</label>
                <input class="form-control mb-4" type="password" name="password" placeholder="admin123">
                <button class="btn btn-primary btn-rounded w-100">Accedi</button>
            </form>
        </div>
    </div>
    """
    return render_template_string(BASE_HTML, content=html)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# =========================================================
# DASHBOARD
# =========================================================
@app.route("/")
@login_required
def dashboard():
    pagamenti_tutti = PagamentoCliente.query.all()
    scaduti = sum(1 for p in pagamenti_tutti if stato_pagamento(p)[0] == "scaduto")
    in_scadenza = sum(1 for p in pagamenti_tutti if stato_pagamento(p)[0] == "in_scadenza")
    html = f"""
    <div class="topbar">
        <div><h1 class="page-title">Dashboard</h1><p class="muted mb-0">Panoramica rapida delle attività e delle scadenze</p></div>
    </div>
    <div class="quick-actions">
        <a class="quick-action" href="/nuovo_cliente"><i class="bi bi-person-plus"></i> Nuovo cliente</a>
        <a class="quick-action" href="/nuovo_immobile"><i class="bi bi-house-add"></i> Nuovo immobile</a>
        <a class="quick-action" href="/nuovo_appuntamento"><i class="bi bi-calendar-plus"></i> Nuovo appuntamento</a>
        <a class="quick-action" href="/pagamenti"><i class="bi bi-cash-coin"></i> Controlla pagamenti</a>
    </div>
    <div class="row g-4">
        <div class="col-md-4"><div class="soft-card metric"><div class="icon"><i class="bi bi-houses"></i></div><p>Immobili</p><h2>{Immobile.query.count()}</h2></div></div>
        <div class="col-md-4"><div class="soft-card metric"><div class="icon"><i class="bi bi-people"></i></div><p>Pazienti / Clienti</p><h2>{Cliente.query.count()}</h2></div></div>
        <div class="col-md-4"><div class="soft-card metric"><div class="icon"><i class="bi bi-calendar-check"></i></div><p>Appuntamenti</p><h2>{Appuntamento.query.count()}</h2></div></div>
        <div class="col-md-6"><a href="/pagamenti" class="text-decoration-none text-dark"><div class="soft-card metric"><div class="icon"><i class="bi bi-exclamation-triangle"></i></div><p>Pagamenti scaduti</p><h2>{scaduti}</h2></div></a></div>
        <div class="col-md-6"><a href="/pagamenti" class="text-decoration-none text-dark"><div class="soft-card metric"><div class="icon"><i class="bi bi-hourglass-split"></i></div><p>Pagamenti in scadenza</p><h2>{in_scadenza}</h2></div></a></div>
    </div>
    """
    return render_template_string(BASE_HTML, content=html)

# =========================================================
# IMMOBILI
# =========================================================
@app.route("/immobili")
@login_required
def immobili():
    righe = ""
    for i in Immobile.query.order_by(Immobile.id.desc()).all():
        clienti_html = " ".join([f'<span class="pill"><i class="bi bi-person"></i>{c.nome}</span>' for c in i.clienti]) or '<span class="muted">Nessuno</span>'
        righe += f"""
        <tr onclick="window.location='/immobile/{i.id}'">
            <td><span class="pill">{i.codice}</span></td><td><b>{i.titolo}</b><br><span class="muted">{i.indirizzo or ''}</span></td>
            <td>{i.citta or ''}</td><td><b>{euro(i.prezzo or 0)}</b></td><td>{clienti_html}</td>
        </tr>"""
    html = f"""
    <div class="topbar"><div><h1 class="page-title">Immobili</h1><p class="muted mb-0">Elenco proprietà</p></div><a href="/nuovo_immobile" class="btn btn-primary btn-rounded"><i class="bi bi-plus-lg"></i> Nuovo immobile</a></div>
    <div class="soft-card p-4"><div class="table-responsive"><table class="table table-hover align-middle"><thead><tr><th>Codice</th><th>Immobile</th><th>Città</th><th>Prezzo</th><th>Collegati</th></tr></thead><tbody>{righe}</tbody></table></div></div>
    """
    return render_template_string(BASE_HTML, content=html)


@app.route("/nuovo_immobile", methods=["GET", "POST"])
@login_required
def nuovo_immobile():
    if request.method == "POST":
        immobile = Immobile(
            codice=genera_codice(), titolo=request.form.get("titolo"), descrizione=request.form.get("descrizione"),
            citta=request.form.get("citta"), indirizzo=request.form.get("indirizzo"), prezzo=float(request.form.get("prezzo") or 0),
            metri_quadri=int(request.form.get("metri_quadri") or 0), camere=int(request.form.get("camere") or 0),
            bagni=int(request.form.get("bagni") or 0), stato=request.form.get("stato")
        )
        db.session.add(immobile); db.session.commit()
        for file in request.files.getlist("foto"):
            nome = salva_file(file, "immobile_foto")
            if nome: db.session.add(FotoImmobile(immobile_id=immobile.id, filename=nome))
        for file in request.files.getlist("allegati"):
            nome = salva_file(file, "immobile_allegato")
            if nome: db.session.add(AllegatoImmobile(immobile_id=immobile.id, filename=nome))
        db.session.commit(); flash("Immobile creato")
        return redirect(url_for("dettaglio_immobile", id=immobile.id))
    html = form_immobile_html("Nuovo immobile", {}, "/nuovo_immobile", True)
    return render_template_string(BASE_HTML, content=html)


def form_immobile_html(titolo, immobile, action, upload=False, immobile_id=None):
    foto_esistenti = ""
    allegati_esistenti = ""
    if immobile_id:
        foto = FotoImmobile.query.filter_by(immobile_id=immobile_id).all()
        allegati = AllegatoImmobile.query.filter_by(immobile_id=immobile_id).all()
        if foto:
            foto_esistenti = "<div class='col-12'><label class='form-label'>Foto già caricate</label><div class='row g-2'>"
            for f in foto:
                foto_esistenti += f"""
                <div class='col-md-4'>
                    <div class='file-tile'>
                        <span><img class='thumb-admin me-2' src='/uploads/{f.filename}'><br><small>{f.filename}</small></span>
                        <label class='text-danger'><input type='checkbox' name='elimina_foto' value='{f.id}'> Elimina</label>
                    </div>
                </div>"""
            foto_esistenti += "</div></div>"
        if allegati:
            allegati_esistenti = "<div class='col-12'><label class='form-label'>Allegati già caricati</label>"
            for a in allegati:
                allegati_esistenti += f"""
                <div class='file-tile'>
                    <span><i class='bi bi-paperclip'></i> <a href='/uploads/{a.filename}' target='_blank'>{a.filename}</a></span>
                    <label class='text-danger'><input type='checkbox' name='elimina_allegati' value='{a.id}'> Elimina</label>
                </div>"""
            allegati_esistenti += "</div>"

    upload_fields = """
                <div class="col-md-6"><label class="form-label">Aggiungi nuove foto</label><input type="file" name="foto" multiple class="form-control"></div>
                <div class="col-md-6"><label class="form-label">Aggiungi nuovi allegati immobile</label><input type="file" name="allegati" multiple class="form-control"></div>
    """ if upload else ""
    enctype = 'enctype="multipart/form-data"' if upload else ''
    return f"""
    <div class="topbar"><div><h1 class="page-title">{titolo}</h1><p class="muted mb-0">Compila i dati principali</p></div></div>
    <div class="soft-card p-4">
        <form method="POST" action="{action}" {enctype}>
            <div class="row g-3">
                <div class="col-md-8"><label class="form-label">Titolo</label><input class="form-control" name="titolo" value="{immobile.get('titolo','')}"></div>
                <div class="col-md-4"><label class="form-label">Stato</label><input class="form-control" name="stato" value="{immobile.get('stato','')}"></div>
                <div class="col-12"><label class="form-label">Descrizione</label><textarea class="form-control" name="descrizione" rows="4">{immobile.get('descrizione','')}</textarea></div>
                <div class="col-md-6"><label class="form-label">Città</label><input class="form-control" name="citta" value="{immobile.get('citta','')}"></div>
                <div class="col-md-6"><label class="form-label">Indirizzo</label><input class="form-control" name="indirizzo" value="{immobile.get('indirizzo','')}"></div>
                <div class="col-md-3"><label class="form-label">Prezzo</label><input class="form-control" name="prezzo" value="{immobile.get('prezzo','')}"></div>
                <div class="col-md-3"><label class="form-label">MQ</label><input class="form-control" name="metri_quadri" value="{immobile.get('metri_quadri','')}"></div>
                <div class="col-md-3"><label class="form-label">Camere</label><input class="form-control" name="camere" value="{immobile.get('camere','')}"></div>
                <div class="col-md-3"><label class="form-label">Bagni</label><input class="form-control" name="bagni" value="{immobile.get('bagni','')}"></div>
                {foto_esistenti}
                {allegati_esistenti}
                {upload_fields}
            </div>
            <button class="btn btn-success btn-rounded mt-4"><i class="bi bi-check2"></i> Salva</button>
        </form>
    </div>"""


@app.route("/immobile/<int:id>")
@login_required
def dettaglio_immobile(id):
    immobile = Immobile.query.get_or_404(id)
    foto = FotoImmobile.query.filter_by(immobile_id=id).all()
    allegati = AllegatoImmobile.query.filter_by(immobile_id=id).all()
    gallery = "".join([f'<img class="gallery-img" src="/uploads/{f.filename}">' for f in foto]) or '<p class="muted">Nessuna foto caricata.</p>'
    files = "".join([f'<a class="file-tile" href="/uploads/{a.filename}" target="_blank"><span><i class="bi bi-paperclip"></i> {a.filename}</span><i class="bi bi-box-arrow-up-right"></i></a>' for a in allegati]) or '<p class="muted">Nessun allegato.</p>'
    clienti_html = "".join([f'<div class="file-tile"><span><b>{c.nome} {c.cognome}</b><br><small>{c.telefono} · {c.email}</small></span><i class="bi bi-person"></i></div>' for c in immobile.clienti]) or '<p class="muted">Nessun paziente/cliente collegato.</p>'
    html = f"""
    <div class="topbar"><div><h1 class="page-title">{immobile.titolo}</h1><p class="muted mb-0">{immobile.codice} · {immobile.citta}</p></div><div class="d-flex gap-2"><a href="/modifica_immobile/{immobile.id}" class="btn btn-warning btn-rounded"><i class="bi bi-pencil"></i> Modifica</a><a href="/elimina_immobile/{immobile.id}" class="btn btn-danger btn-rounded" onclick="return confirm('Eliminare questo immobile? I clienti collegati resteranno salvati ma senza immobile collegato.')"><i class="bi bi-trash"></i> Elimina</a></div></div>
    <div class="row g-4"><div class="col-lg-8"><div class="soft-card detail-hero mb-4"><span class="pill mb-3">{immobile.stato or 'Stato non indicato'}</span><h2>{euro(immobile.prezzo or 0)}</h2><p>{immobile.descrizione or ''}</p><div class="row g-3 mt-2"><div class="col-md-6"><div class="pill"><i class="bi bi-geo-alt"></i>{immobile.indirizzo}</div></div><div class="col-md-2"><div class="pill">{immobile.metri_quadri} MQ</div></div><div class="col-md-2"><div class="pill">{immobile.camere} camere</div></div><div class="col-md-2"><div class="pill">{immobile.bagni} bagni</div></div></div></div><div class="soft-card p-4"><h4>Galleria immagini</h4>{gallery}</div></div><div class="col-lg-4"><div class="soft-card p-4 mb-4"><h4>Pazienti / Clienti collegati</h4>{clienti_html}</div><div class="soft-card p-4"><h4>Allegati immobile</h4>{files}</div></div></div>
    """
    return render_template_string(BASE_HTML, content=html)


@app.route("/elimina_immobile/<int:id>")
@login_required
def elimina_immobile(id):
    immobile = Immobile.query.get_or_404(id)

    for foto in list(immobile.foto):
        elimina_file_fisico(foto.filename)
    for allegato in list(immobile.allegati):
        elimina_file_fisico(allegato.filename)

    for cliente in immobile.clienti:
        cliente.immobile_id = None

    db.session.delete(immobile)
    db.session.commit()
    flash("Immobile eliminato")
    return redirect(url_for("immobili"))


@app.route("/modifica_immobile/<int:id>", methods=["GET", "POST"])
@login_required
def modifica_immobile(id):
    immobile = Immobile.query.get_or_404(id)
    if request.method == "POST":
        for campo in ["titolo", "descrizione", "citta", "indirizzo", "stato"]:
            setattr(immobile, campo, request.form.get(campo))
        immobile.prezzo = float(request.form.get("prezzo") or 0)
        immobile.metri_quadri = int(request.form.get("metri_quadri") or 0)
        immobile.camere = int(request.form.get("camere") or 0)
        immobile.bagni = int(request.form.get("bagni") or 0)

        for foto_id in request.form.getlist("elimina_foto"):
            foto = FotoImmobile.query.get(int(foto_id))
            if foto and foto.immobile_id == immobile.id:
                elimina_file_fisico(foto.filename)
                db.session.delete(foto)

        for allegato_id in request.form.getlist("elimina_allegati"):
            allegato = AllegatoImmobile.query.get(int(allegato_id))
            if allegato and allegato.immobile_id == immobile.id:
                elimina_file_fisico(allegato.filename)
                db.session.delete(allegato)

        for file in request.files.getlist("foto"):
            nome = salva_file(file, "immobile_foto")
            if nome:
                db.session.add(FotoImmobile(immobile_id=immobile.id, filename=nome))

        for file in request.files.getlist("allegati"):
            nome = salva_file(file, "immobile_allegato")
            if nome:
                db.session.add(AllegatoImmobile(immobile_id=immobile.id, filename=nome))

        db.session.commit(); flash("Immobile modificato")
        return redirect(url_for("dettaglio_immobile", id=id))
    html = form_immobile_html("Modifica immobile", immobile.__dict__, f"/modifica_immobile/{id}", True, id)
    return render_template_string(BASE_HTML, content=html)

# =========================================================
# PAZIENTI / CLIENTI
# =========================================================
@app.route("/clienti")
@login_required
def clienti():
    righe = ""
    for c in Cliente.query.order_by(Cliente.id.desc()).all():
        immobile = c.immobile.titolo if c.immobile else "—"
        allegati = len(c.allegati)
        righe += f"""
        <tr onclick="window.location='/cliente/{c.id}'">
            <td><b>{c.nome} {c.cognome}</b></td><td>{c.telefono or ''}</td><td>{c.email or ''}</td><td>{immobile}</td><td><span class="pill"><i class="bi bi-paperclip"></i>{allegati}</span></td>
        </tr>"""
    html = f"""
    <div class="topbar"><div><h1 class="page-title">Pazienti / Clienti</h1><p class="muted mb-0">Anagrafiche, note e allegati personali</p></div><a href="/nuovo_cliente" class="btn btn-primary btn-rounded"><i class="bi bi-plus-lg"></i> Nuovo</a></div>
    <div class="soft-card p-4"><div class="table-responsive"><table class="table table-hover align-middle"><thead><tr><th>Nome</th><th>Telefono</th><th>Email</th><th>Immobile</th><th>Allegati</th></tr></thead><tbody>{righe}</tbody></table></div></div>
    """
    return render_template_string(BASE_HTML, content=html)


def opzioni_immobili(selected_id=None):
    html = '<option value="">Nessun immobile</option>'
    for i in Immobile.query.all():
        selected = "selected" if selected_id == i.id else ""
        html += f'<option value="{i.id}" {selected}>{i.titolo}</option>'
    return html


def salva_allegati_cliente(cliente_id):
    for file in request.files.getlist("allegati_cliente"):
        nome = salva_file(file, "paziente_allegato")
        if nome:
            db.session.add(AllegatoCliente(cliente_id=cliente_id, filename=nome))


@app.route("/nuovo_cliente", methods=["GET", "POST"])
@login_required
def nuovo_cliente():
    if request.method == "POST":
        cliente = Cliente(
            nome=request.form.get("nome"), cognome=request.form.get("cognome"), telefono=request.form.get("telefono"),
            email=request.form.get("email"), note=request.form.get("note"),
            immobile_id=int(request.form.get("immobile_id")) if request.form.get("immobile_id") else None
        )
        db.session.add(cliente); db.session.commit()
        salva_allegati_cliente(cliente.id)
        db.session.commit(); flash("Paziente / cliente creato")
        return redirect(url_for("dettaglio_cliente", id=cliente.id))
    html = form_cliente_html("Nuovo paziente / cliente", {}, "/nuovo_cliente", True)
    return render_template_string(BASE_HTML, content=html)


def form_cliente_html(titolo, cliente, action, upload=True):
    return f"""
    <div class="topbar"><div><h1 class="page-title">{titolo}</h1><p class="muted mb-0">Dati, note e documenti allegati</p></div></div>
    <div class="soft-card p-4">
        <form method="POST" action="{action}" enctype="multipart/form-data">
            <div class="row g-3">
                <div class="col-md-6"><label class="form-label">Nome</label><input class="form-control" name="nome" value="{cliente.get('nome','')}"></div>
                <div class="col-md-6"><label class="form-label">Cognome</label><input class="form-control" name="cognome" value="{cliente.get('cognome','')}"></div>
                <div class="col-md-6"><label class="form-label">Telefono</label><input class="form-control" name="telefono" value="{cliente.get('telefono','')}"></div>
                <div class="col-md-6"><label class="form-label">Email</label><input class="form-control" name="email" value="{cliente.get('email','')}"></div>
                <div class="col-12"><label class="form-label">Note</label><textarea class="form-control" name="note" rows="4">{cliente.get('note','')}</textarea></div>
                <div class="col-md-6"><label class="form-label">Immobile collegato</label><select class="form-select" name="immobile_id">{opzioni_immobili(cliente.get('immobile_id'))}</select></div>
                <div class="col-md-6"><label class="form-label">Allegati paziente / cliente</label><input type="file" name="allegati_cliente" multiple class="form-control"><small class="muted">PDF, immagini, Word, Excel e TXT.</small></div>
            </div>
            <button class="btn btn-success btn-rounded mt-4"><i class="bi bi-check2"></i> Salva</button>
        </form>
    </div>"""


@app.route("/cliente/<int:id>")
@login_required
def dettaglio_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    immobile_html = f'<a class="file-tile" href="/immobile/{cliente.immobile.id}"><span><b>{cliente.immobile.titolo}</b><br><small>{cliente.immobile.citta}</small></span><i class="bi bi-arrow-right"></i></a>' if cliente.immobile else '<p class="muted">Nessun immobile collegato.</p>'
    allegati_html = "".join([f'<a class="file-tile" href="/uploads/{a.filename}" target="_blank"><span><i class="bi bi-paperclip"></i> {a.filename}<br><small>Caricato il {a.caricato_il.strftime("%d/%m/%Y") if a.caricato_il else ""}</small></span><i class="bi bi-box-arrow-up-right"></i></a>' for a in cliente.allegati]) or '<p class="muted">Nessun allegato caricato.</p>'

    righe_pagamenti = ""
    for p in sorted(cliente.pagamenti, key=lambda x: (x.data_scadenza or "9999-99-99", x.id)):
        _, classe, stato = stato_pagamento(p)
        righe_pagamenti += f"""
        <tr class="{classe}">
            <td><b>{p.descrizione or 'Pagamento'}</b><br><small>{p.note or ''}</small></td>
            <td>{euro(p.importo or 0)}</td>
            <td>{formato_data(p.data_scadenza)}</td>
            <td>{formato_data(p.data_pagamento)}</td>
            <td>{stato}</td>
            <td class="text-end">
                <a class="btn btn-sm btn-success" href="/pagamento/{p.id}/segna_pagato">Pagato oggi</a>
                <form method="POST" action="/pagamento/{p.id}/prolunga" class="d-inline-flex gap-1 align-items-center ms-1">
                    <input type="date" class="form-control form-control-sm" name="nuova_scadenza" style="width:145px" required>
                    <button class="btn btn-sm btn-outline-primary">Prolunga</button>
                </form>
                <a class="btn btn-sm btn-outline-danger ms-1" href="/pagamento/{p.id}/elimina" onclick="return confirm('Eliminare questo pagamento?')">Elimina</a>
            </td>
        </tr>"""
    if not righe_pagamenti:
        righe_pagamenti = '<tr><td colspan="6" class="muted">Nessun pagamento inserito.</td></tr>'

    pagamenti_html = f"""
    <div class="soft-card p-4 mt-4">
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h4 class="mb-0">Pagamenti</h4>
            <span class="muted">Rosso = scaduto, giallo = entro 15 giorni, verde = ok/pagato.</span>
        </div>
        <div class="table-responsive mb-4">
            <table class="table align-middle">
                <thead><tr><th>Descrizione</th><th>Importo</th><th>Scadenza</th><th>Pagamento</th><th>Stato</th><th></th></tr></thead>
                <tbody>{righe_pagamenti}</tbody>
            </table>
        </div>
        <form method="POST" action="/cliente/{cliente.id}/nuovo_pagamento">
            <div class="row g-2 align-items-end">
                <div class="col-md-3"><label class="form-label">Descrizione</label><input class="form-control" name="descrizione" placeholder="Es. rata, affitto, acconto"></div>
                <div class="col-md-2"><label class="form-label">Importo</label><input class="form-control" type="number" step="0.01" name="importo"></div>
                <div class="col-md-2"><label class="form-label">Scadenza</label><input class="form-control" type="date" name="data_scadenza" required><small class="muted">Appare in agenda</small></div>
                <div class="col-md-2"><label class="form-label">Data pagamento</label><input class="form-control" type="date" name="data_pagamento"></div>
                <div class="col-md-3"><label class="form-label">Note</label><input class="form-control" name="note"></div>
                <div class="col-12"><button class="btn btn-primary btn-rounded"><i class="bi bi-plus-lg"></i> Aggiungi pagamento</button></div>
            </div>
        </form>
    </div>"""

    html = f"""
    <div class="topbar"><div><h1 class="page-title">{cliente.nome} {cliente.cognome}</h1><p class="muted mb-0">Scheda paziente / cliente</p></div><div class="d-flex gap-2"><a href="/modifica_cliente/{cliente.id}" class="btn btn-warning btn-rounded"><i class="bi bi-pencil"></i> Modifica</a><a href="/elimina_cliente/{cliente.id}" class="btn btn-danger btn-rounded" onclick="return confirm('Eliminare questo cliente con allegati e pagamenti?')"><i class="bi bi-trash"></i> Elimina</a></div></div>
    <div class="row g-4"><div class="col-lg-7"><div class="soft-card detail-hero"><div class="row g-3"><div class="col-md-6"><span class="pill"><i class="bi bi-telephone"></i>{cliente.telefono or 'Telefono non indicato'}</span></div><div class="col-md-6"><span class="pill"><i class="bi bi-envelope"></i>{cliente.email or 'Email non indicata'}</span></div></div><hr><h4>Note</h4><p>{cliente.note or 'Nessuna nota.'}</p></div>{pagamenti_html}</div><div class="col-lg-5"><div class="soft-card p-4 mb-4"><h4>Immobile collegato</h4>{immobile_html}</div><div class="soft-card p-4"><h4>Allegati paziente / cliente</h4>{allegati_html}</div></div></div>
    """
    return render_template_string(BASE_HTML, content=html)



@app.route("/cliente/<int:id>/nuovo_pagamento", methods=["POST"])
@login_required
def nuovo_pagamento_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    pagamento = PagamentoCliente(
        cliente_id=cliente.id,
        descrizione=request.form.get("descrizione") or "Pagamento",
        importo=float(request.form.get("importo") or 0),
        data_scadenza=request.form.get("data_scadenza"),
        data_pagamento=request.form.get("data_pagamento") or None,
        note=request.form.get("note")
    )
    db.session.add(pagamento)
    db.session.commit()
    flash("Pagamento aggiunto: se ha una scadenza e non è pagato, ora compare anche in agenda")
    return redirect(url_for("dettaglio_cliente", id=cliente.id))


@app.route("/pagamento/<int:id>/segna_pagato")
@login_required
def segna_pagamento_pagato(id):
    pagamento = PagamentoCliente.query.get_or_404(id)
    pagamento.data_pagamento = datetime.today().strftime("%Y-%m-%d")
    db.session.commit()
    flash("Pagamento segnato come pagato")
    return redirect(url_for("dettaglio_cliente", id=pagamento.cliente_id))


@app.route("/pagamento/<int:id>/prolunga", methods=["POST"])
@login_required
def prolunga_pagamento(id):
    pagamento = PagamentoCliente.query.get_or_404(id)
    pagamento.data_scadenza = request.form.get("nuova_scadenza") or pagamento.data_scadenza
    db.session.commit()
    flash("Scadenza pagamento aggiornata: agenda aggiornata automaticamente")
    return redirect(url_for("dettaglio_cliente", id=pagamento.cliente_id))


@app.route("/pagamento/<int:id>/elimina")
@login_required
def elimina_pagamento(id):
    pagamento = PagamentoCliente.query.get_or_404(id)
    cliente_id = pagamento.cliente_id
    db.session.delete(pagamento)
    db.session.commit()
    flash("Pagamento eliminato")
    return redirect(url_for("dettaglio_cliente", id=cliente_id))


@app.route("/elimina_cliente/<int:id>")
@login_required
def elimina_cliente(id):
    cliente = Cliente.query.get_or_404(id)

    for allegato in list(cliente.allegati):
        elimina_file_fisico(allegato.filename)

    db.session.delete(cliente)
    db.session.commit()
    flash("Paziente / cliente eliminato")
    return redirect(url_for("clienti"))


@app.route("/modifica_cliente/<int:id>", methods=["GET", "POST"])
@login_required
def modifica_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    if request.method == "POST":
        for campo in ["nome", "cognome", "telefono", "email", "note"]:
            setattr(cliente, campo, request.form.get(campo))
        cliente.immobile_id = int(request.form.get("immobile_id")) if request.form.get("immobile_id") else None
        salva_allegati_cliente(cliente.id)
        db.session.commit(); flash("Paziente / cliente modificato")
        return redirect(url_for("dettaglio_cliente", id=id))
    html = form_cliente_html("Modifica paziente / cliente", cliente.__dict__, f"/modifica_cliente/{id}")
    return render_template_string(BASE_HTML, content=html)

# =========================================================
# PAGAMENTI
# =========================================================
@app.route("/pagamenti")
@login_required
def pagamenti():
    righe = ""
    pagamenti_lista = PagamentoCliente.query.order_by(PagamentoCliente.data_scadenza.asc(), PagamentoCliente.id.asc()).all()
    for p in pagamenti_lista:
        _, classe, stato = stato_pagamento(p)
        cliente_nome = f"{p.cliente.nome or ''} {p.cliente.cognome or ''}".strip() if p.cliente else "Cliente eliminato"
        immobile = p.cliente.immobile.titolo if p.cliente and p.cliente.immobile else "—"
        giorni = giorni_alla_scadenza(p)
        giorni_html = "—" if giorni is None else (f"Scaduto da {abs(giorni)} giorni" if giorni < 0 else f"Tra {giorni} giorni")
        cliente_link = f"/cliente/{p.cliente_id}" if p.cliente else "#"
        righe += f"""
        <tr class="{classe}" onclick="window.location='{cliente_link}'">
            <td><b>{cliente_nome}</b><br><small>{immobile}</small></td>
            <td><b>{p.descrizione or 'Pagamento'}</b><br><small>{p.note or ''}</small></td>
            <td>{euro(p.importo or 0)}</td>
            <td>{formato_data(p.data_scadenza)}<br><small>{giorni_html}</small></td>
            <td>{formato_data(p.data_pagamento)}</td>
            <td>{stato}</td>
            <td class="text-end">
                <a class="btn btn-sm btn-success" href="/pagamento/{p.id}/segna_pagato" onclick="event.stopPropagation()">Pagato oggi</a>
                <a class="btn btn-sm btn-outline-danger ms-1" href="/pagamento/{p.id}/elimina" onclick="event.stopPropagation(); return confirm('Eliminare questo pagamento?')">Elimina</a>
            </td>
        </tr>"""
    if not righe:
        righe = '<tr><td colspan="7" class="muted">Nessun pagamento inserito.</td></tr>'

    html = f"""
    <div class="topbar">
        <div><h1 class="page-title">Pagamenti</h1><p class="muted mb-0">Tutte le prossime scadenze dei clienti</p></div>
    </div>
    <div class="soft-card p-4 mb-4">
        <div class="d-flex gap-2 flex-wrap">
            <span class="badge text-bg-danger p-2">Rosso: scaduto / da pagare</span>
            <span class="badge text-bg-warning p-2">Giallo: manca poco, entro 15 giorni</span>
            <span class="badge text-bg-success p-2">Verde: ok o già pagato</span>
        </div>
    </div>
    <div class="soft-card p-4">
        <div class="table-responsive">
            <table class="table table-hover align-middle">
                <thead><tr><th>Cliente</th><th>Pagamento</th><th>Importo</th><th>Scadenza</th><th>Pagato il</th><th>Stato</th><th></th></tr></thead>
                <tbody>{righe}</tbody>
            </table>
        </div>
    </div>
    """
    return render_template_string(BASE_HTML, content=html)



def pagamento_titolo_agenda(p):
    cliente_nome = f"{p.cliente.nome or ''} {p.cliente.cognome or ''}".strip() if p.cliente else "Cliente"
    return f"Scadenza pagamento - {cliente_nome}"


def pagamento_luogo_agenda(p):
    if p.cliente and p.cliente.immobile:
        return p.cliente.immobile.titolo or ""
    return "Pagamento cliente"


def pagamento_note_agenda(p):
    return f"{p.descrizione or 'Pagamento'} · {euro(p.importo or 0)}" + (f" · {p.note}" if p.note else "")

# =========================================================
# AGENDA
# =========================================================
@app.route("/agenda")
@login_required
def agenda():
    settimana_offset = int(request.args.get("week", 0))
    oggi = datetime.today()
    inizio_settimana = oggi - timedelta(days=oggi.weekday()) + timedelta(weeks=settimana_offset)
    fine_settimana = inizio_settimana + timedelta(days=6)
    traduzioni = {"Monday":"Lunedì","Tuesday":"Martedì","Wednesday":"Mercoledì","Thursday":"Giovedì","Friday":"Venerdì","Saturday":"Sabato","Sunday":"Domenica"}
    giorni = [{"nome":traduzioni.get((inizio_settimana+timedelta(days=i)).strftime("%A")),"numero":(inizio_settimana+timedelta(days=i)).day,"mese":(inizio_settimana+timedelta(days=i)).month,"data":(inizio_settimana+timedelta(days=i)).strftime("%Y-%m-%d")} for i in range(7)]
    ore_html = "".join([f'<div class="ora-slot">{h:02d}:00</div>' for h in range(8, 21)])
    colonne = ""
    appuntamenti = Appuntamento.query.all()
    pagamenti_con_scadenza = PagamentoCliente.query.filter(PagamentoCliente.data_scadenza.isnot(None), PagamentoCliente.data_pagamento.is_(None)).all()

    riepilogo_items = []
    for giorno in giorni:
        eventi = ""
        # Appuntamenti manuali
        for a in appuntamenti:
            if a.data == giorno["data"] and a.ora:
                try:
                    hh, mm = a.ora.split(":")
                    top = ((int(hh) - 8) * 78) + (int(mm) * 1.3)
                    if top < 0: top = 0
                    eventi += f'<div class="evento agenda-appointment" style="top:{top}px;"><b><i class="bi bi-clock"></i> {a.ora}</b><br>{a.titolo}<br><small><i class="bi bi-geo-alt"></i> {a.luogo or ""}</small></div>'
                    riepilogo_items.append((giorno["data"], a.ora, a.titolo, a.luogo or "", "Appuntamento"))
                except Exception:
                    pass
        # Scadenze pagamento automatiche: vengono mostrate alle 09:00 nell'agenda
        payment_index = 0
        for p in pagamenti_con_scadenza:
            if p.data_scadenza == giorno["data"]:
                top = 78 + (payment_index * 92)  # 09:00, con impilamento se ci sono più scadenze
                cliente_link = f"/cliente/{p.cliente_id}" if p.cliente else "/pagamenti"
                eventi += f'<div class="evento agenda-payment" style="top:{top}px;" onclick="window.location=\'{cliente_link}\'"><b><i class="bi bi-cash-coin"></i> Scadenza pagamento</b><br>{pagamento_titolo_agenda(p)}<br><small>{pagamento_note_agenda(p)}</small></div>'
                riepilogo_items.append((giorno["data"], "09:00", pagamento_titolo_agenda(p), pagamento_note_agenda(p), "Pagamento"))
                payment_index += 1
        colonne += f'<div class="giorno-colonna"><div class="giorno-header"><div><div class="giorno-nome">{giorno["nome"]}</div><div class="giorno-data">{giorno["numero"]}/{giorno["mese"]}</div></div></div><div class="giorno-body">{eventi}</div></div>'

    riepilogo_items.sort(key=lambda x: (x[0], x[1]))
    riepilogo_html = ""
    for data, ora, titolo, dettaglio, tipo in riepilogo_items:
        badge = "text-bg-warning" if tipo == "Pagamento" else "text-bg-primary"
        riepilogo_html += f'<div class="agenda-item"><span class="badge {badge} mb-2">{tipo}</span><strong>{formato_data(data)} · {ora}</strong><div>{titolo}</div><small class="muted">{dettaglio}</small></div>'
    if not riepilogo_html:
        riepilogo_html = '<div class="empty-state">Nessun appuntamento o pagamento in scadenza in questa settimana.</div>'

    html = f"""
    <div class="topbar"><div><h1 class="page-title">Agenda</h1><p class="muted mb-0">{inizio_settimana.strftime('%d/%m/%Y')} - {fine_settimana.strftime('%d/%m/%Y')}</p></div><div class="d-flex gap-2 flex-wrap"><a href="/agenda?week={settimana_offset-1}" class="btn btn-light btn-rounded">←</a><a href="/agenda?week=0" class="btn btn-light btn-rounded">Oggi</a><a href="/agenda?week={settimana_offset+1}" class="btn btn-light btn-rounded">→</a><a href="/nuovo_appuntamento" class="btn btn-primary btn-rounded"><i class="bi bi-plus-lg"></i> Nuovo</a></div></div>
    <div class="hint-box mb-3"><i class="bi bi-info-circle"></i> Le scadenze dei pagamenti non ancora saldati compaiono automaticamente in agenda nel giorno della scadenza, alle 09:00.</div>
    <div class="calendar-wrapper"><div class="calendar-grid"><div class="ore-colonna"><div style="height:70px;"></div>{ore_html}</div><div class="giorni-container">{colonne}</div></div></div>
    <div class="section-title mt-4"><h4 class="mb-0">Riepilogo settimana</h4><span class="muted">Appuntamenti + scadenze</span></div>
    <div class="agenda-list">{riepilogo_html}</div>
    """
    return render_template_string(BASE_HTML, content=html)


@app.route("/nuovo_appuntamento", methods=["GET", "POST"])
@login_required
def nuovo_appuntamento():
    if request.method == "POST":
        appuntamento = Appuntamento(titolo=request.form.get("titolo"), data=request.form.get("data"), ora=request.form.get("ora"), luogo=request.form.get("luogo"), note=request.form.get("note"))
        db.session.add(appuntamento); db.session.commit(); flash("Appuntamento creato")
        return redirect(url_for("agenda"))
    html = """
    <div class="topbar"><div><h1 class="page-title">Nuovo appuntamento</h1><p class="muted mb-0">Inserisci data, ora e luogo</p></div></div>
    <div class="soft-card p-4"><form method="POST"><div class="row g-3"><div class="col-md-6"><label class="form-label">Titolo</label><input class="form-control" name="titolo"></div><div class="col-md-3"><label class="form-label">Data</label><input class="form-control" type="date" name="data"></div><div class="col-md-3"><label class="form-label">Ora</label><input class="form-control" type="time" name="ora"></div><div class="col-12"><label class="form-label">Luogo</label><input class="form-control" name="luogo"></div><div class="col-12"><label class="form-label">Note</label><textarea class="form-control" name="note" rows="4"></textarea></div></div><button class="btn btn-success btn-rounded mt-4">Salva</button></form></div>
    """
    return render_template_string(BASE_HTML, content=html)

# =========================================================
# PWA / MOBILE APP
# =========================================================
@app.route("/manifest.json")
def manifest():
    return Response('''{
        "name": "Gestionale",
        "short_name": "Gestionale",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f8fafc",
        "theme_color": "#111827",
        "icons": []
    }''', mimetype="application/manifest+json")


@app.route("/service-worker.js")
def service_worker():
    return Response('''self.addEventListener('install', event => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {});''', mimetype="application/javascript")


# =========================================================
# FILES
# =========================================================
@app.route("/uploads/<filename>")
@login_required
def uploads(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# =========================================================
# START
# =========================================================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True, host="0.0.0.0", port=5000)
