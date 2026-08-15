"""
Loan application routes.
"""

from fastapi import APIRouter

from backend.models.schemas import LoanApplicationRequest, LoanApplicationResponse
from backend.services.loan_service import LoanService

router = APIRouter()


@router.post("/submit", response_model=LoanApplicationResponse)
async def submit_application(request: LoanApplicationRequest):
    """Submit a loan application/lead."""
    app_id = LoanService.create_loan_application(request.customer_id, {
        "loan_type": request.loan_type,
        "amount": request.amount,
        "employment": request.employment
    })
    
    return LoanApplicationResponse(
        application_id=app_id,
        message="Application submitted successfully. A loan specialist will contact you soon."
    )
