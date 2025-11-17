"""
Database Schemas for Workflow Automation Platform

Each Pydantic model corresponds to a MongoDB collection (lowercased class name).
Use these for validation and to power the database viewer via GET /schema.
"""
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, EmailStr

class Organization(BaseModel):
    name: str = Field(..., description="Organization name")
    domain: Optional[str] = Field(None, description="Email domain for auto-join")

class Plan(BaseModel):
    key: Literal["starter", "growth", "pro"] = Field(..., description="Plan identifier")
    name: str = Field(..., description="Display name")
    price_usd: float = Field(..., ge=0, description="Monthly price in USD")
    features: List[str] = Field(default_factory=list, description="Included features list")

class Subscription(BaseModel):
    org_id: str = Field(..., description="Organization ID")
    plan_key: Literal["starter", "growth", "pro"]
    status: Literal["active", "past_due", "canceled"] = "active"

class User(BaseModel):
    name: str
    email: EmailStr
    org_id: Optional[str] = None
    role: Literal["requester", "approver", "admin"] = "requester"
    is_active: bool = True

class FormField(BaseModel):
    key: str = Field(..., description="Unique field key")
    label: str
    type: Literal["text", "number", "date", "select", "currency", "textarea", "file"] = "text"
    required: bool = False
    options: Optional[List[str]] = None

class Form(BaseModel):
    name: str
    description: Optional[str] = None
    fields: List[FormField]
    org_id: Optional[str] = None

class WorkflowStep(BaseModel):
    name: str
    type: Literal["approval", "auto"] = "approval"
    approver_role: Optional[Literal["approver", "admin"]] = "approver"
    on_approve: Optional[str] = Field(None, description="Next step logic (simple)")

class Workflow(BaseModel):
    name: str
    description: Optional[str] = None
    form_id: Optional[str] = None
    steps: List[WorkflowStep] = Field(default_factory=list)
    org_id: Optional[str] = None
    category: Optional[str] = Field(None, description="e.g., Finance, HR")

class Submission(BaseModel):
    form_id: str
    workflow_id: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "approved", "rejected", "archived"] = "pending"
    requester_id: Optional[str] = None

class Approval(BaseModel):
    submission_id: str
    step_name: Optional[str] = None
    actor_id: Optional[str] = None
    action: Literal["approved", "rejected"]
    comment: Optional[str] = None

class Document(BaseModel):
    submission_id: str
    title: str
    content_type: str = "application/pdf"
    storage: Literal["inline", "external"] = "inline"
    data_base64: Optional[str] = Field(None, description="Base64 if inline storage")
    external_url: Optional[str] = None
    archived: bool = False

class Template(BaseModel):
    key: Literal["invoice_approval", "expense_reimbursement", "purchase_order"]
    name: str
    description: Optional[str] = None
    form: Form
    workflow: Workflow

# Note: The database viewer will fetch these via GET /schema
