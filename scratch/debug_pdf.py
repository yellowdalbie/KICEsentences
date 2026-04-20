import pypdfium2 as pdfium
import sys

pdf_path = 'PDF_Ref/2026.6모_16.pdf'
pdf = pdfium.PdfDocument(pdf_path)
page = pdf[0]
tp = page.get_textpage()
page_width, page_height = page.get_size()

target = "16."
search = tp.search(target)
occ = search.get_next()
while occ:
    index, count = occ
    charbox = tp.get_charbox(index + count - 1)
    text = tp.get_text_range(index, count)
    print(f"Found '{text}' at PDF coords: {charbox}, Top-down Y: {page_height - charbox[3]}")
    occ = search.get_next()
pdf.close()
