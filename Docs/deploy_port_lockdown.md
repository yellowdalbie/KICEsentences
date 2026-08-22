# 8181 포트 앱 노출 제거 + 구 주소 자동 리다이렉트 절차

> 대상 서버: 158.180.90.73 (Oracle Cloud, Ubuntu) / 앱: pm2 `think-lynx-dashboard`
> 작성: 2026-08-22

## 배경

`dashboard.py` 는 온라인 모드에서 `SESSION_COOKIE_SECURE = True` 이므로 세션 쿠키에
`Secure` 플래그가 붙는다. 브라우저는 평문 HTTP 응답의 Secure 쿠키를 저장하지 않기 때문에
`http://158.180.90.73:8181` 로 직접 접속하면 로그인 요청은 200 으로 성공해도 세션이
유지되지 않는다. HTTPS 도메인(`https://www.thinklynx.xyz`)에서는 정상 동작한다.

Secure 플래그를 끄면 도메인 쪽 세션까지 평문 전송이 가능해지므로, 대신 **IP 직접 접속
경로에서 앱을 걷어내고 도메인으로 자동 유도**한다.

## 구조 변경 요약

| | 변경 전 | 변경 후 |
|---|---|---|
| Flask 앱 | `0.0.0.0:8181` (공인 IP 직접 노출) | `127.0.0.1:8182` (루프백 전용) |
| 공인 IP `:80` | 도메인 사이트 내용이 그대로 노출 | 301 → `https://www.thinklynx.xyz` |
| 공인 IP `:8181` | Flask 앱 (로그인 실패, nginx 우회 가능) | nginx 301 → `https://www.thinklynx.xyz` |
| 도메인 443 | nginx → `127.0.0.1:8181` | nginx → `127.0.0.1:8182` |

8181 은 계속 열려 있지만 그 포트에 붙는 것은 리다이렉트만 하는 nginx 서버 블록이다.
앱이 응답하지 않으므로 `X-Forwarded-For` 위조로 로그인 레이트리밋을 우회하는 경로도 함께 막힌다.

## 절차

### 1. 최신 코드 반영

```bash
cd ~/KICEsentences && git pull --ff-only
```

`ecosystem.config.js` 가 `KICE_HOST=127.0.0.1`, `KICE_PORT=8182` 로 바뀐다.

### 2. nginx: 프록시 대상 포트 변경 + 리다이렉트 블록 추가

```bash
# 기존 사이트 설정에서 8181 을 참조하는 파일 확인
grep -rln "8181" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/
sudo cp -a /etc/nginx/sites-available /root/nginx-backup-$(date +%F)   # 백업

# 위에서 나온 파일의 proxy_pass 포트를 8182 로 변경 (파일명은 실제 결과로 대체)
sudo sed -i 's|proxy_pass http://127.0.0.1:8181|proxy_pass http://127.0.0.1:8182|g' \
  /etc/nginx/sites-available/<사이트파일>

# default_server 중복 여부 확인 (충돌하면 nginx -t 실패)
grep -rn "default_server" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/
sudo rm -f /etc/nginx/sites-enabled/default    # 위에서 충돌이 잡힐 때만

sudo cp deploy/nginx/redirect-ip.conf /etc/nginx/sites-available/redirect-ip.conf
sudo ln -sf /etc/nginx/sites-available/redirect-ip.conf /etc/nginx/sites-enabled/
sudo nginx -t
```

### 3. 앱 재시작 → nginx 리로드 (연달아 실행, 다운타임 수 초)

```bash
pm2 restart think-lynx-dashboard --update-env && sudo systemctl reload nginx
sleep 5
ss -ltnp | grep -E "8181|8182"
#   127.0.0.1:8182 → python3 (앱)
#   0.0.0.0:8181   → nginx
```

### 4. 검증

```bash
curl -sI https://www.thinklynx.xyz/app        | head -3   # 200
curl -sI http://158.180.90.73/                | head -3   # 301 → https://www.thinklynx.xyz/
curl -sI http://158.180.90.73:8181/           | head -3   # 301 → https://www.thinklynx.xyz/
curl -sI http://158.180.90.73:8181/app        | head -3   # 301 → https://www.thinklynx.xyz/app
```

브라우저에서 `http://158.180.90.73:8181` 접속 → 도메인으로 이동 → 로그인 정상 동작 확인.

### 5. Oracle Cloud Security List 정리 (웹 콘솔)

Networking → Virtual Cloud Networks → VCN → Security Lists → Default Security List
→ Ingress Rules 에서 **5555** 규칙 삭제. **8181 은 유지**한다(리다이렉트용으로 계속 필요).
80/443/22 도 유지.

## 롤백

```bash
sudo rm /etc/nginx/sites-enabled/redirect-ip.conf
sudo sed -i 's|proxy_pass http://127.0.0.1:8182|proxy_pass http://127.0.0.1:8181|g' \
  /etc/nginx/sites-available/<사이트파일>
# ecosystem.config.js 의 KICE_PORT 를 8181, KICE_HOST 를 0.0.0.0 으로 되돌린 뒤
pm2 restart think-lynx-dashboard --update-env && sudo systemctl reload nginx
```

## 참고

- 로컬 Mac 개발 환경은 pm2/ecosystem 을 쓰지 않고 `python3 dashboard.py` 로 실행하므로
  기존대로 `http://localhost:8181` 이다. 포트 8182 는 **서버 내부 전용**.
- 오프라인 패키지(`OFFLINE_MODE=1`)는 `SESSION_COOKIE_SECURE` 가 꺼지므로 영향 없다.
