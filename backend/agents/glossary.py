"""
Static financial glossary.

This is a deterministic keyword lookup, not vector-based RAG — there's
no embedding model or vector store here. It's an honest, lightweight
stand-in for "explain this term" questions: real fixed definitions,
matched by keyword, with no LLM guessing at what a term means.
"""

from __future__ import annotations

GLOSSARY_HI: dict[str, str] = {
    "EMI": "EMI (Equated Monthly Instalment) har mahine loan ke against di jaane wali fixed raashi hai, "
           "jisme principal aur interest dono shaamil hote hain, jab tak loan poora chukta na ho jaaye.",
    "Principal": "Principal woh original amount hai jo aapne loan ke roop mein liya tha, interest jodne se pehle.",
    "Interest": "Interest paisa udhaar lene ki cost hai, jo outstanding principal par percentage ke roop mein "
                "charge kiya jaata hai, aam taur par annual rate ke roop mein.",
    "Outstanding": "Outstanding amount woh raashi hai jo aapko loan par abhi bhi chukani baaki hai "
                   "(principal aur accrued interest milakar).",
    "Tenure": "Tenure woh total duration hai jiske andar loan chukane ka schedule banaya gaya hai, "
              "aam taur par months ya years mein.",
    "Foreclosure": "Foreclosure ka matlab hai loan ko uski tenure khatam hone se pehle hi ek saath poora "
                   "chuka dena, further EMIs ke bajaay.",
    "Prepayment": "Prepayment ka matlab hai loan ke principal mein schedule se pehle extra lump sum jama "
                  "karna. Isse loan poora close nahi hota, lekin outstanding balance kam ho jaata hai — "
                  "jisse EMI ya remaining tenure kam ho sakti hai.",
    "Processing Fee": "Processing fee ek one-time charge hai jo lender loan application handle aur approve "
                       "karne ke liye leta hai, aam taur par loan amount ka ek chhota percentage.",
    "Fixed Rate": "Fixed interest rate poori loan tenure ke liye same rehta hai, isliye market rates badalne "
                  "par bhi aapki EMI nahi badalti.",
    "Floating Rate": "Floating (variable) interest rate loan tenure ke dauraan market benchmark rates ke "
                     "saath upar-neeche hoti rehti hai, isliye aapki EMI time ke saath badal sakti hai.",
    "LTV": "LTV (Loan-to-Value) woh percentage hai jo loan amount ko finance ki ja rahi asset ki value ke "
           "against darshata hai — jaise, 80% LTV wala home loan property ki 80% value cover karta hai.",
    "Credit Score": "Credit score ek numeric rating hai (India mein aam taur par 300-900) jo aapki credit "
                    "history ko summarise karta hai, jise lenders yeh assess karne ke liye use karte hain "
                    "ki aap loan chukane mein kitne reliable hain.",
}

GLOSSARY: dict[str, str] = {
    "EMI": "EMI (Equated Monthly Instalment) is the fixed amount you pay every month toward a loan, "
           "covering both principal and interest, until the loan is fully repaid.",
    "Principal": "The principal is the original amount borrowed, before any interest is added.",
    "Interest": "Interest is the cost of borrowing money, charged as a percentage of the outstanding "
                "principal, usually expressed as an annual rate.",
    "Outstanding": "The outstanding amount is how much of the principal (plus any accrued interest) "
                   "you still owe on a loan.",
    "Tenure": "Tenure is the total duration over which a loan is scheduled to be repaid, usually "
              "expressed in months or years.",
    "Foreclosure": "Foreclosure means repaying a loan in full before the end of its tenure, closing it "
                   "out completely in one go rather than through further EMIs.",
    "Prepayment": "Prepayment is paying an extra lump sum toward a loan's principal, ahead of schedule. "
                  "It doesn't close the loan, but reduces the outstanding balance — which can lower "
                  "either the EMI or the remaining tenure.",
    "Processing Fee": "A processing fee is a one-time charge a lender takes for handling and approving "
                       "a loan application, usually a small percentage of the loan amount.",
    "Fixed Rate": "A fixed interest rate stays the same for the entire loan tenure, so your EMI doesn't "
                  "change even if market rates move.",
    "Floating Rate": "A floating (variable) interest rate moves up or down with market benchmark rates "
                     "over the loan's tenure, so your EMI can change over time.",
    "LTV": "LTV (Loan-to-Value) is the loan amount expressed as a percentage of the value of the asset "
           "being financed — for example, an 80% LTV home loan covers 80% of the property's value.",
    "Credit Score": "A credit score is a numeric rating (typically 300-900 in India) summarising your "
                    "credit history, used by lenders to assess how likely you are to repay a loan.",
}

# Map lookup keywords -> canonical glossary key (handles Hindi/Hinglish phrasing too).
_KEYWORD_TO_TERM: dict[str, str] = {
    "emi": "EMI", "installment": "EMI", "installment kya": "EMI",
    "principal": "Principal", "mool": "Principal",
    "interest": "Interest", "byaj": "Interest",
    "outstanding": "Outstanding", "baki amount": "Outstanding",
    "tenure": "Tenure", "avadhi": "Tenure",
    "foreclosure": "Foreclosure", "foreclose": "Foreclosure",
    "prepayment": "Prepayment", "prepay": "Prepayment",
    "processing fee": "Processing Fee",
    "fixed rate": "Fixed Rate", "fixed interest": "Fixed Rate",
    "floating rate": "Floating Rate", "floating interest": "Floating Rate", "variable rate": "Floating Rate",
    "ltv": "LTV", "loan to value": "LTV",
    "credit score": "Credit Score", "cibil": "Credit Score",
}


def find_glossary_term(text: str) -> str | None:
    """Return the canonical glossary term mentioned in text, if any."""
    text_lower = text.lower()
    # Longer keywords first so "processing fee" wins over a bare "fee" match, etc.
    for keyword in sorted(_KEYWORD_TO_TERM, key=len, reverse=True):
        if keyword in text_lower:
            return _KEYWORD_TO_TERM[keyword]
    return None


def get_definition(term: str, language: str = "en") -> str | None:
    source = GLOSSARY_HI if language == "hi" else GLOSSARY
    return source.get(term)
