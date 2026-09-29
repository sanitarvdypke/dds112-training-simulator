"""Load a local classifier through the same API as the teacher interface."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import httpx


def main():
    parser=argparse.ArgumentParser(description="Импорт ЕКП через API")
    parser.add_argument("path", type=Path)
    parser.add_argument("--filename")
    parser.add_argument("--api", default="http://localhost:8000/api")
    args=parser.parse_args()
    data=args.path.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    with httpx.Client(base_url=args.api, timeout=60) as client:
        response=client.post("/auth/login", json={
            "email":os.getenv("IMPORT_EMAIL","teacher@example.local"),
            "password":os.getenv("IMPORT_PASSWORD","Teacher123!")})
        response.raise_for_status()
        client.headers["Authorization"]="Bearer "+response.json()["access_token"]
        # Reuse this source if previously committed under its actual filename.
        filename=args.filename or args.path.name
        offset=0
        version=None
        while True:
            page=client.get("/imports/classifier",params={"offset":offset,"limit":100})
            page.raise_for_status()
            payload=page.json()
            version=next((r for r in payload["items"] if r["source_sha256"]==digest and r["filename"]==filename and r["status"]=="COMMITTED"),None)
            if version or offset+100>=payload["total"]:
                break
            offset+=100
        if version is None:
            response=client.post("/imports/classifier/stage", files={"file":(filename,data)})
            response.raise_for_status()
            version=response.json()
            if version["validation_errors"]:
                print(json.dumps(version,ensure_ascii=False,indent=2))
                raise SystemExit("Ошибки исходника: версия не подтверждена")
            response=client.post(f'/imports/classifier/{version["import_id"]}/commit')
            response.raise_for_status()
            version=response.json()
        check=client.get(f'/imports/classifier/{version["import_id"]}/entries')
        check.raise_for_status()
        assert check.json()["total"]==version["statistics"]["incident_count"]
        print(json.dumps({"import_id":version["import_id"],"filename":filename,"source_sha256":digest,
                          "status":version["status"],"statistics":version["statistics"]},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
