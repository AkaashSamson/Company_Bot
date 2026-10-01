import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from docling.document_converter import DocumentConverter

def main():
    doc_path = project_root / "input" / "HR_Policy_Manual.docx"
    converter = DocumentConverter()
    result = converter.convert(doc_path)
    document = result.document
    
    labels = set()
    for item, level in document.iterate_items():
        label_obj = getattr(item, "label", "")
        label_val = str(getattr(label_obj, "value", label_obj) or "").strip().lower()
        labels.add(label_val)
            
    print(f"\nUnique labels found in HR_Policy_Manual: {labels}")

if __name__ == "__main__":
    main()
