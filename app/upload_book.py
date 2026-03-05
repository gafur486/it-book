import os
import sys
import requests

# NOTE: Ин версия API token надорад. Агар мехоҳед, баъд token илова мекунем.
# Ҳоло беҳтараш аз /admin upload истифода баред.

def main():
    if len(sys.argv) < 5:
        print("Usage: python upload_book.py <BASE_URL> <TITLE> <PDF_PATH> <GRADE>")
        sys.exit(1)

    base_url, title, pdf_path, grade = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    if not os.path.exists(pdf_path):
        print("ERROR: PDF file not found:", pdf_path)
        sys.exit(1)

    # Ин танҳо намуна аст — барои upload аз админ беҳтар аст
    print("This script is a placeholder in v1. Use /admin panel upload.")
    print("BASE_URL:", base_url, "TITLE:", title, "GRADE:", grade)

if __name__ == "__main__":
    main()