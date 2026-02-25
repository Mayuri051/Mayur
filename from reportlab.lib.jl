from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Drawing, Rect, String, Line

# Create PDF
file_path = "Smart_Scan_and_Go_System.pdf"
doc = SimpleDocTemplate(file_path, pagesize=A4)
elements = []

styles = getSampleStyleSheet()
title_style = styles["Heading1"]
section_style = styles["Heading2"]
normal_style = styles["BodyText"]

# Title
elements.append(Paragraph("Smart Scan and Go System", title_style))
elements.append(Spacer(1, 0.3 * inch))

# 1. Introduction
elements.append(Paragraph("1. Introduction", section_style))
elements.append(Spacer(1, 0.2 * inch))
elements.append(Paragraph(
    "The Smart Scan and Go System is a digital retail solution that allows customers "
    "to scan items while shopping and complete payment instantly without waiting in long queues. "
    "It improves customer convenience and enhances store efficiency.",
    normal_style
))
elements.append(Spacer(1, 0.3 * inch))

# 2. Key Digital Features
elements.append(Paragraph("2. Key Digital Features", section_style))
elements.append(Spacer(1, 0.2 * inch))

features = [
    "Customer Registration and Secure Login",
    "Real-Time Product Scanning (Barcode/RFID)",
    "Automatic Bill Generation",
    "Instant Digital Payment Integration",
    "Inventory Synchronization",
    "Digital Receipt Generation",
    "Exit Verification System",
    "Analytics Dashboard for Management"
]

elements.append(ListFlowable(
    [ListItem(Paragraph(f, normal_style)) for f in features],
    bulletType='bullet'
))
elements.append(Spacer(1, 0.3 * inch))

# 3. Digital Workflow
elements.append(Paragraph("3. Digital Workflow", section_style))
elements.append(Spacer(1, 0.2 * inch))

workflow = [
    "Login to mobile app upon entering store",
    "Scan items while placing in cart",
    "View real-time bill update",
    "Complete instant digital payment",
    "Receive digital receipt & QR confirmation",
    "Exit store via QR verification"
]

elements.append(ListFlowable(
    [ListItem(Paragraph(step, normal_style)) for step in workflow],
    bulletType='bullet'
))
elements.append(Spacer(1, 0.3 * inch))

# Workflow Illustration
elements.append(Paragraph("Workflow Illustration", styles["Heading3"]))
elements.append(Spacer(1, 0.2 * inch))

drawing = Drawing(400, 120)
drawing.add(Rect(10, 60, 80, 30))
drawing.add(String(25, 75, "Scan"))
drawing.add(Rect(120, 60, 80, 30))
drawing.add(String(135, 75, "Auto Bill"))
drawing.add(Rect(230, 60, 80, 30))
drawing.add(String(255, 75, "Pay"))
drawing.add(Rect(340, 60, 80, 30))
drawing.add(String(365, 75, "Exit"))
drawing.add(Line(90, 75, 120, 75))
drawing.add(Line(200, 75, 230, 75))
drawing.add(Line(310, 75, 340, 75))

elements.append(drawing)
elements.append(Spacer(1, 0.3 * inch))

# 4. SWOT Analysis
elements.append(Paragraph("4. SWOT Analysis", section_style))
elements.append(Spacer(1, 0.2 * inch))

swot_data = [
    ["Strengths", "Faster checkout, customer convenience, reduced staff workload"],
    ["Weaknesses", "Requires smartphone/infrastructure, risk of scanning errors"],
    ["Opportunities", "Expansion to malls, AI-based offers, loyalty integration"],
    ["Threats", "Cybersecurity risks, theft, system failures"]
]

table = Table(swot_data, colWidths=[100, 350])
table.setStyle(TableStyle([
    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
]))

elements.append(table)
elements.append(Spacer(1, 0.3 * inch))

# 5. Technical Architecture
elements.append(Paragraph("5. Technical Architecture", section_style))
elements.append(Spacer(1, 0.2 * inch))

architecture = [
    "Frontend: Mobile App / Smart Cart Interface",
    "Backend: Cloud Database with Secure Authentication",
    "Scanning Technology: Barcode / QR / RFID",
    "Payment Gateway: Secure API Integration",
    "Analytics Dashboard: Sales & Customer Insights"
]

elements.append(ListFlowable(
    [ListItem(Paragraph(a, normal_style)) for a in architecture],
    bulletType='bullet'
))
elements.append(Spacer(1, 0.3 * inch))

# 6. Conclusion
elements.append(Paragraph("6. Conclusion", section_style))
elements.append(Spacer(1, 0.2 * inch))
elements.append(Paragraph(
    "The Smart Scan and Go System modernizes retail shopping by eliminating long queues "
    "and enabling instant checkout. It provides scalability, efficiency, and enhanced "
    "customer satisfaction through digital transformation.",
    normal_style
))

doc.build(elements)

print("PDF successfully generated:", file_path)