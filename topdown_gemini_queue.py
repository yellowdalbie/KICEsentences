#!/usr/bin/env python3
"""
탑다운: Gemini 작업 큐 폴더 생성
===================================
Phase 1 진단 결과에서 B4/D1 플래그된 파일을 추출하고
Gemini 해설 재작성을 위한 작업 폴더에 {코드}_문제.md / {코드}_해설.md 쌍으로 복사.

폴더 구조:
  gemini_queue/
    B4_방법어없음/    — step_title에 how(방법)가 불명확한 파일  (13쌍)
    D1_단일스텝/      — 10번 이상 문항인데 스텝이 1개뿐인 파일 (222쌍)

파일 명명 규칙:
  {고유코드}_문제.md  ← MD_Ref 원본 문제 (읽기 전용 참고)
  {고유코드}_해설.md  ← Sol 기존 해설  (Gemini가 수정 후 저장)
  (같은 코드이므로 파일 브라우저에서 항상 인접 정렬됨)

수정 완료 후 Sol 원위치 동기화:
  python3 topdown_gemini_queue.py --sync
"""

import json, os, shutil, sys
from pathlib import Path

DIAG_FILE = 'topdown_diagnosis.json'
QUEUE_DIR = 'gemini_queue'

FOLDERS = {
    'B4': f'{QUEUE_DIR}/B4_방법어없음',
    'D1': f'{QUEUE_DIR}/D1_단일스텝',
}


# ── 경로 변환 ────────────────────────────────────────────────

def sol_to_ref(sol_path: str) -> str:
    """
    Sol 경로 → MD_Ref 경로.
    특수: Sol/2028/2028.예시_XX.md → MD_Ref/2028.예시_XX.md (루트에 있음)
    """
    p = Path(sol_path)
    if p.parts[1] == '2028':          # Sol/2028/...
        return f'MD_Ref/{p.name}'     # MD_Ref/2028.예시_XX.md (루트)
    return sol_path.replace('Sol/', 'MD_Ref/', 1)


def file_code(sol_path: str) -> str:
    """고유코드: Sol/2024/2024수능_15.md → 2024수능_15"""
    return Path(sol_path).stem


# ── 대상 파일 수집 ───────────────────────────────────────────

def collect_targets(diag: dict) -> dict:
    """
    B4/D1 플래그된 Sol 파일 경로 수집.
    B4 우선: B4에 포함된 파일은 D1 목록에서 제외.
    """
    b4_files: set[str] = set()
    d1_files: set[str] = set()

    for fp, rec in diag['files'].items():
        for fl in rec['file_flags']:
            if fl['code'] == 'D1':
                d1_files.add(fp)
        for sr in rec['steps']:
            for fl in sr['flags']:
                if fl['code'] == 'B4':
                    b4_files.add(fp)

    d1_files -= b4_files   # 중복 방지: B4가 우선
    return {'B4': b4_files, 'D1': d1_files}


# ── 복사 ─────────────────────────────────────────────────────

def copy_pair(sol_path: str, dest_dir: str) -> tuple[bool, list[str]]:
    """
    (MD_Ref, Sol) 쌍을 dest_dir에
    {코드}_문제.md / {코드}_해설.md 로 복사.
    반환: (성공여부, 오류메시지 목록)
    """
    ref_path  = sol_to_ref(sol_path)
    code      = file_code(sol_path)
    dest_prob = os.path.join(dest_dir, f'{code}_문제.md')
    dest_sol  = os.path.join(dest_dir, f'{code}_해설.md')

    ok, msgs = True, []

    if os.path.exists(ref_path):
        shutil.copy2(ref_path, dest_prob)
    else:
        msgs.append(f'MD_Ref 없음: {ref_path}')
        ok = False

    if os.path.exists(sol_path):
        shutil.copy2(sol_path, dest_sol)
    else:
        msgs.append(f'Sol 없음: {sol_path}')
        ok = False

    return ok, msgs


# ── 역동기화 (수정된 해설 → Sol 원위치) ─────────────────────

def sync_back(diag: dict):
    """
    gemini_queue 내 _해설.md 파일 중
    원본 Sol보다 mtime이 최신인 것만 Sol 경로로 복사.
    """
    # code → sol_path 역매핑
    code_to_sol = {file_code(fp): fp for fp in diag['files']}

    synced, skipped, errors = 0, 0, 0

    for flag_code, folder in FOLDERS.items():
        if not os.path.isdir(folder):
            continue
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith('_해설.md'):
                continue
            code     = fname[: -len('_해설.md')]
            src      = os.path.join(folder, fname)
            sol_path = code_to_sol.get(code)

            if not sol_path:
                print(f'  [SKIP] {fname} — Sol 경로 매핑 없음')
                skipped += 1
                continue
            if not os.path.exists(sol_path):
                print(f'  [SKIP] {fname} — Sol 파일 없음: {sol_path}')
                errors += 1
                continue

            if os.path.getmtime(src) > os.path.getmtime(sol_path):
                shutil.copy2(src, sol_path)
                print(f'  [SYNC] {code} → {sol_path}')
                synced += 1
            else:
                skipped += 1

    print(f'\n역동기화: {synced}개 반영 / {skipped}개 변경없음 / {errors}개 오류')


# ── 메인 ─────────────────────────────────────────────────────

def main():
    with open(DIAG_FILE, encoding='utf-8') as f:
        diag = json.load(f)

    # ── --sync: 수정된 해설 → Sol 역동기화 ────────────────────
    if '--sync' in sys.argv:
        print('=== Gemini 큐 → Sol 역동기화 ===')
        sync_back(diag)
        return

    # ── 큐 폴더 생성 ──────────────────────────────────────────
    targets = collect_targets(diag)

    print('=' * 55)
    print('탑다운: Gemini 작업 큐 폴더 생성')
    print('=' * 55)
    print(f'  B4 (방법어없음): {len(targets["B4"])}쌍')
    print(f'  D1 (단일스텝):   {len(targets["D1"])}쌍')
    print()

    total_ok = total_err = 0

    for flag_code in ('B4', 'D1'):
        dest_dir  = FOLDERS[flag_code]
        label     = os.path.basename(dest_dir)
        file_set  = targets[flag_code]
        os.makedirs(dest_dir, exist_ok=True)

        ok_cnt = err_cnt = 0
        err_log = []

        for sol_path in sorted(file_set):
            ok, msgs = copy_pair(sol_path, dest_dir)
            if ok:
                ok_cnt += 1
            else:
                err_cnt += 1
                err_log.append((sol_path, msgs))

        print(f'[{label}]')
        print(f'  복사 성공: {ok_cnt}쌍  /  오류: {err_cnt}개')
        for sol_path, msgs in err_log:
            for m in msgs:
                print(f'  ⚠  {m}')

        total_ok  += ok_cnt
        total_err += err_cnt

    # ── 결과 요약 ─────────────────────────────────────────────
    print()
    print(f'전체: {total_ok}쌍 ({total_ok * 2}개 파일) 복사 완료'
          + (f'  /  {total_err}개 오류' if total_err else ''))
    print()
    print('생성된 폴더:')
    for flag_code, folder in FOLDERS.items():
        n = len(targets[flag_code])
        print(f'  {folder}/   ({n}쌍)')
    print()
    print('파일 명명 규칙:')
    print('  {코드}_문제.md  — 원본 문제 (MD_Ref 복사본)')
    print('  {코드}_해설.md  — 기존 해설 (Gemini 수정 후 저장)')
    print()
    print('작업 완료 후 Sol 원위치 동기화:')
    print('  python3 topdown_gemini_queue.py --sync')


if __name__ == '__main__':
    main()
