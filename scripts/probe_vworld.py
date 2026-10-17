"""브이월드 연결 진단. 인증 URL·키·공간 원본 저장 금지."""
import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from local_config import load


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 인증 쿼리가 다른 주소로 전달되지 않도록 리다이렉트 차단.
        return None


def main():
    load()
    key = os.environ.get("VWORLD_API_KEY", "")
    if not key:
        raise SystemExit(".env.local VWORLD_API_KEY 설정 필요")
    domain = os.environ.get("VWORLD_DOMAIN", "http://127.0.0.1:5173").strip()
    registered = urlsplit(domain)
    if (registered.scheme not in {"http", "https"} or not registered.hostname
            or registered.username or registered.password or registered.query or registered.fragment
            or len(domain) > 256 or any(c.isspace() for c in domain)):
        raise SystemExit("VWORLD_DOMAIN에 등록된 서비스 URL 설정 필요")
    parameters = {
        "service": "data", "version": "2.0", "request": "GetFeature",
        "data": "LT_C_SPBD", "geomFilter": "BOX(127.0525,37.5430,127.0555,37.5455)",
        "size": "10", "page": "1", "format": "json", "crs": "EPSG:4326",
        "domain": domain, "key": key,
    }
    try:
        request = Request("https://api.vworld.kr/req/data?" + urlencode(parameters),
                          headers={"Referer": domain + "/"})
        with build_opener(NoRedirect).open(request, timeout=30) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000 or key.encode() in raw:
            raise ValueError("응답 안전 검사 실패")
        response = json.loads(raw)["response"]
        status = response.get("status")
        if status != "OK":
            code = response.get("error", {}).get("code", "UNKNOWN")
            # 외부 오류 원문에 인증 정보가 포함될 가능성을 차단.
            safe = code if isinstance(code, str) and code.replace("_", "").isupper() and len(code) < 60 else "UNKNOWN"
            raise SystemExit("브이월드 조회 거부: " + safe)
        collection = response["result"]["featureCollection"]
        features = collection["features"]
        print(json.dumps({
            "status": status, "returnedFeatures": len(features),
            "geometryTypes": sorted({f["geometry"]["type"] for f in features}),
            "attributeNames": sorted(features[0]["properties"]) if features else [],
            "rawSaved": False,
        }, ensure_ascii=False))
    except HTTPError as error:
        raise SystemExit(f"브이월드 HTTP {error.code}") from None
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit("브이월드 통신 또는 응답 형식 오류") from None


if __name__ == "__main__":
    main()
