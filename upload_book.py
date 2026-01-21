import sys
import os
import requests

# Истифода:
# python upload_book.py https://it-book.onrender.com "Номи китоб" "C:\path\book.pdf" 9

def main():
    if len(sys.argv) < 4:
        print("Usage: python upload_book.py <base_url> <title> <pdf_path> [grade]")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    title = sys.argv[2]
    pdf_path = sys.argv[3]
    grade = sys.argv[4] if len(sys.argv) >= 5 else None

    token = os.getenv("ADMIN_TOKEN")
    if not token:
        print("ERROR: ADMIN_TOKEN is not set")
        sys.exit(1)

    url = f"{base_url}/admin/books/upload"
    headers = {"X-Admin-Token": token}
    data = {"title": title}
    if grade:
        data["grade"] = grade

    try:
        with open(pdf_path, "rb") as f:
            files = {"pdf": f}
            r = requests.post(url, data=data, files=files, headers=headers, timeout=120)
        print("STATUS:", r.status_code)
        print(r.text)
    except FileNotFoundError:
        print("ERROR: PDF file not found:", pdf_path)

if __name__ == "__main__":
    main()
