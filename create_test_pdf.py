import sys
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

c = canvas.Canvas("input/sample.pdf", pagesize=letter)
c.setFont("Helvetica-Bold", 16)
c.drawString(72, 750, "1. Leave Policy")

c.setFont("Helvetica", 12)
c.drawString(72, 720, "This is a paragraph about leave.")

# A very basic fake table (just text visually aligned)
c.drawString(72, 690, "Type          Days")
c.drawString(72, 670, "Sick          5")
c.drawString(72, 650, "Annual        10")

c.drawString(300, 50, "1") # Page num
c.save()
