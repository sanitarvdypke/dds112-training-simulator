"""Optional visual QA helper: pip install pymupdf; python tests/verify_pdf.py."""
import httpx
import fitz
c=httpx.Client(base_url="http://localhost:8000/api")
r=c.post("/auth/login",json={"email":"teacher@example.local","password":"Teacher123!"})
c.headers["Authorization"]="Bearer "+r.json()["access_token"]
rid=c.get("/reports/assessments").json()[0]["id"]
data=c.get(f"/reports/assessment/{rid}.pdf").content
doc=fitz.open(stream=data,filetype="pdf")
assert "Отчёт учебного тренажёра ДДС-112" in doc[0].get_text()
doc[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save("/tmp/report-qa.png")
print("PDF: Cyrillic text extracted; 1 page rendered for visual QA")
