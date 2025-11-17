import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId
from datetime import datetime

from database import db, create_document, get_documents

app = FastAPI(title="Workflow Automation Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Utilities ----------

def to_str_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    d = dict(doc)
    if d.get("_id"):
        d["id"] = str(d.pop("_id"))
    # convert nested ObjectIds
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
        if isinstance(v, list):
            d[k] = [str(x) if isinstance(x, ObjectId) else x for x in v]
    return d

# Simple PDF generation using reportlab
try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

# ---------- Health & Schema ----------

@app.get("/")
def read_root():
    return {"message": "Workflow Automation Platform Backend"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

@app.get("/schema")
def get_schema():
    # Expose schemas for database viewer
    import schemas as app_schemas
    models = [
        m for m in dir(app_schemas)
        if not m.startswith("_") and isinstance(getattr(app_schemas, m), type)
    ]
    out = {}
    for name in models:
        model = getattr(app_schemas, name)
        try:
            if issubclass(model, BaseModel):
                out[name] = model.model_json_schema()
        except Exception:
            continue
    return out

# ---------- Pricing ----------

@app.get("/pricing")
def get_pricing():
    return {
        "plans": [
            {
                "key": "starter",
                "name": "Starter",
                "price_usd": 0,
                "features": [
                    "Unlimited forms",
                    "Single-step approvals",
                    "Basic dashboards",
                ],
            },
            {
                "key": "growth",
                "name": "Growth",
                "price_usd": 49,
                "features": [
                    "Multi-step workflows",
                    "PDF generation",
                    "Document archive",
                    "Email notifications",
                ],
            },
            {
                "key": "pro",
                "name": "Pro",
                "price_usd": 149,
                "features": [
                    "SLA & escalations",
                    "Advanced analytics",
                    "Priority support",
                    "Audit logs",
                ],
            },
        ]
    }

# ---------- Forms ----------

class FormIn(BaseModel):
    name: str
    description: Optional[str] = None
    fields: List[Dict[str, Any]]
    org_id: Optional[str] = None

@app.post("/forms")
def create_form(payload: FormIn):
    form_id = create_document("form", payload.model_dump())
    return {"id": form_id}

@app.get("/forms")
def list_forms(org_id: Optional[str] = None):
    q: Dict[str, Any] = {}
    if org_id:
        q["org_id"] = org_id
    forms = [to_str_id(f) for f in get_documents("form", q)]
    return {"items": forms}

@app.get("/forms/{form_id}")
def get_form(form_id: str):
    doc = db["form"].find_one({"_id": ObjectId(form_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Form not found")
    return to_str_id(doc)

# ---------- Workflows ----------

class WorkflowIn(BaseModel):
    name: str
    description: Optional[str] = None
    form_id: Optional[str] = None
    steps: List[Dict[str, Any]] = []
    org_id: Optional[str] = None
    category: Optional[str] = None

@app.post("/workflows")
def create_workflow(payload: WorkflowIn):
    wf_id = create_document("workflow", payload.model_dump())
    return {"id": wf_id}

@app.get("/workflows")
def list_workflows(org_id: Optional[str] = None, category: Optional[str] = None):
    q: Dict[str, Any] = {}
    if org_id:
        q["org_id"] = org_id
    if category:
        q["category"] = category
    wfs = [to_str_id(w) for w in get_documents("workflow", q)]
    return {"items": wfs}

# ---------- Submissions & Approvals ----------

class SubmissionIn(BaseModel):
    form_id: str
    workflow_id: Optional[str] = None
    data: Dict[str, Any] = {}
    requester_id: Optional[str] = None

@app.post("/submissions")
def create_submission(payload: SubmissionIn):
    sub = payload.model_dump()
    sub["status"] = "pending"
    sub_id = create_document("submission", sub)
    return {"id": sub_id, "status": "pending"}

@app.get("/submissions")
def list_submissions(status: Optional[str] = None, workflow_id: Optional[str] = None):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if workflow_id:
        q["workflow_id"] = workflow_id
    subs = [to_str_id(s) for s in get_documents("submission", q)]
    return {"items": subs}

class ApprovalIn(BaseModel):
    submission_id: str
    action: str  # "approved" or "rejected"
    actor_id: Optional[str] = None
    comment: Optional[str] = None

@app.post("/approvals")
def act_on_submission(payload: ApprovalIn):
    if payload.action not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid action")
    sid = payload.submission_id
    sub = db["submission"].find_one({"_id": ObjectId(sid)})
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    new_status = "approved" if payload.action == "approved" else "rejected"
    db["submission"].update_one({"_id": ObjectId(sid)}, {"$set": {"status": new_status, "updated_at": datetime.utcnow()}})
    # record approval log
    create_document("approval", {
        "submission_id": sid,
        "action": payload.action,
        "actor_id": payload.actor_id,
        "comment": payload.comment or "",
    })
    return {"id": sid, "status": new_status}

# ---------- PDF Generation & Documents ----------

class GeneratePDFIn(BaseModel):
    submission_id: str
    title: Optional[str] = None

@app.post("/submissions/{submission_id}/generate-pdf")
def generate_pdf(submission_id: str, payload: GeneratePDFIn):
    if not REPORTLAB_AVAILABLE:
        raise HTTPException(status_code=500, detail="PDF generator not available")
    sub = db["submission"].find_one({"_id": ObjectId(submission_id)})
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    # Create PDF in-memory
    from io import BytesIO
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    c.setTitle(payload.title or "Submission PDF")
    width, height = LETTER
    y = height - 72
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, payload.title or "Submission Summary")
    y -= 24
    c.setFont("Helvetica", 10)
    c.drawString(72, y, f"Submission ID: {submission_id}")
    y -= 16
    c.drawString(72, y, f"Status: {sub.get('status', 'unknown')}")
    y -= 24
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Data:")
    y -= 18
    c.setFont("Helvetica", 10)
    for k, v in sub.get("data", {}).items():
        line = f"- {k}: {v}"
        c.drawString(80, y, line[:110])
        y -= 14
        if y < 72:
            c.showPage(); y = height - 72
    c.showPage()
    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()

    import base64
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    doc_id = create_document("document", {
        "submission_id": submission_id,
        "title": payload.title or "Generated PDF",
        "content_type": "application/pdf",
        "storage": "inline",
        "data_base64": b64,
        "archived": False,
    })
    return {"id": doc_id, "submission_id": submission_id}

@app.post("/documents/{document_id}/archive")
def archive_document(document_id: str):
    res = db["document"].update_one({"_id": ObjectId(document_id)}, {"$set": {"archived": True, "updated_at": datetime.utcnow()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"id": document_id, "archived": True}

@app.get("/documents")
def list_documents(submission_id: Optional[str] = None, archived: Optional[bool] = None):
    q: Dict[str, Any] = {}
    if submission_id:
        q["submission_id"] = submission_id
    if archived is not None:
        q["archived"] = archived
    docs = [to_str_id(d) for d in get_documents("document", q)]
    return {"items": docs}

# ---------- Dashboard ----------

@app.get("/dashboard/summary")
def dashboard_summary():
    total_forms = db["form"].count_documents({})
    total_workflows = db["workflow"].count_documents({})
    total_submissions = db["submission"].count_documents({})
    by_status = list(db["submission"].aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]))
    by_status_map = {row.get("_id", "unknown"): row.get("count", 0) for row in by_status}
    recent = [to_str_id(x) for x in db["submission"].find({}).sort("created_at", -1).limit(10)]
    return {
        "totals": {
            "forms": total_forms,
            "workflows": total_workflows,
            "submissions": total_submissions,
        },
        "submissions_by_status": by_status_map,
        "recent_submissions": recent,
    }

# ---------- Pre-built Finance Templates ----------

@app.post("/templates/seed")
def seed_templates():
    # Only seed if not present
    existing = db["template"].count_documents({})
    if existing > 0:
        return {"status": "already_seeded"}

    # Invoice Approval
    invoice_form = {
        "name": "Invoice Approval",
        "description": "Submit vendor invoice for approval",
        "fields": [
            {"key": "vendor", "label": "Vendor", "type": "text", "required": True},
            {"key": "invoice_number", "label": "Invoice #", "type": "text", "required": True},
            {"key": "amount", "label": "Amount", "type": "currency", "required": True},
            {"key": "due_date", "label": "Due Date", "type": "date"},
            {"key": "attachment", "label": "Attachment", "type": "file"},
        ],
    }
    form_id_1 = create_document("form", invoice_form)
    invoice_wf = {
        "name": "Invoice Approval Workflow",
        "description": "Manager approval then finance approval",
        "form_id": form_id_1,
        "category": "Finance",
        "steps": [
            {"name": "Manager Review", "type": "approval", "approver_role": "approver"},
            {"name": "Finance Approval", "type": "approval", "approver_role": "admin"},
        ],
    }
    wf_id_1 = create_document("workflow", invoice_wf)

    # Expense Reimbursement
    expense_form = {
        "name": "Expense Reimbursement",
        "description": "Claim employee expenses",
        "fields": [
            {"key": "employee", "label": "Employee", "type": "text", "required": True},
            {"key": "category", "label": "Category", "type": "select", "options": ["Travel", "Meals", "Office"], "required": True},
            {"key": "amount", "label": "Amount", "type": "currency", "required": True},
            {"key": "notes", "label": "Notes", "type": "textarea"},
        ],
    }
    form_id_2 = create_document("form", expense_form)
    expense_wf = {
        "name": "Expense Reimbursement Workflow",
        "description": "Manager approval",
        "form_id": form_id_2,
        "category": "Finance",
        "steps": [
            {"name": "Manager Review", "type": "approval", "approver_role": "approver"},
        ],
    }
    wf_id_2 = create_document("workflow", expense_wf)

    # Purchase Order
    po_form = {
        "name": "Purchase Order",
        "description": "Create purchase order",
        "fields": [
            {"key": "requester", "label": "Requester", "type": "text", "required": True},
            {"key": "item", "label": "Item", "type": "text", "required": True},
            {"key": "quantity", "label": "Quantity", "type": "number", "required": True},
            {"key": "unit_price", "label": "Unit Price", "type": "currency", "required": True},
        ],
    }
    form_id_3 = create_document("form", po_form)
    po_wf = {
        "name": "Purchase Order Workflow",
        "description": "Manager then finance approval",
        "form_id": form_id_3,
        "category": "Finance",
        "steps": [
            {"name": "Manager Review", "type": "approval", "approver_role": "approver"},
            {"name": "Finance Approval", "type": "approval", "approver_role": "admin"},
        ],
    }
    wf_id_3 = create_document("workflow", po_wf)

    # Save templates collection
    create_document("template", {
        "key": "invoice_approval", "name": "Invoice Approval", "description": "Vendor invoice approval",
        "form": {"id": form_id_1}, "workflow": {"id": wf_id_1}
    })
    create_document("template", {
        "key": "expense_reimbursement", "name": "Expense Reimbursement", "description": "Employee expenses",
        "form": {"id": form_id_2}, "workflow": {"id": wf_id_2}
    })
    create_document("template", {
        "key": "purchase_order", "name": "Purchase Order", "description": "PO creation and approval",
        "form": {"id": form_id_3}, "workflow": {"id": wf_id_3}
    })

    return {"status": "seeded", "forms": [form_id_1, form_id_2, form_id_3]}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
