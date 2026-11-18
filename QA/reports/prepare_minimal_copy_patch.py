"""Prepare a reversible dashboard wording patch without editing its pinned source."""
from pathlib import Path
import difflib
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'.parts-snapshots-20261118-check/2026-Agent_Scope-8f56930af9f2b9b8491b0df6c26ba6c4a4dc8cc5/dashboard'
DEST = ROOT/'.parts-snapshots-20261119-check/dashboard-reviewed'
PATCH = ROOT/'.qa-publish/review-20261119/dashboard-wording.patch'


def main():
    if not DEST.exists():
        shutil.copytree(SOURCE, DEST, ignore=shutil.ignore_patterns('dist', '.git'))
    changes = {
        'src/data/present.ts': {
            "what: '서버끼리 같은 토큰 사용'": "what: '서버 간 자격증명 참조 공유 설정'",
            '승인하지 않은 서버가 연결됐어요': '승인하지 않은 서버가 등록됐어요',
            '에이전트가 이 서버의 도구를 바로 쓸 수 있어서,': '설정만으로 실제 도구 호출 가능 여부는 확정할 수 없어요.',
            '승인하지 않은 서버 ${n}개가 연결됐어요': '승인하지 않은 서버 ${n}개가 등록됐어요',
            '승인할 때와 다른 주소로 연결되고 있어요.': '승인할 때와 다른 주소가 설정돼 있어요.',
            '플러그인을 설치하는 것만으로 에이전트가 쓸 수 있는 도구가 늘어나요.': '등록된 도구가 에이전트에 노출되는지와 실제 호출 가능한지는 별도 확인이 필요해요.',
            '서버 여러 개가 같은 토큰을 써요': '서버 여러 개에 같은 자격증명 참조가 설정됐어요',
            '하나의 인증 토큰을 여러 서버가 같이 쓰고 있어요. 한 서버에서 토큰이 새면 다른 서버까지 함께 뚫려요.': '같은 저장소의 자격증명 참조가 여러 서버에 설정돼 있어요. 실제 비밀값의 동일성이나 인증 성공을 확인한 것은 아니에요. 참조한 자격증명이 유출되면 영향 범위가 커질 수 있어요.',
            '같은 토큰을 쓰는 곳 ${n}건': '같은 자격증명 참조를 공유하는 설정 ${n}건',
            '토큰이 바뀐 주소로 보내지고 있어요': '미승인 주소에 자격증명 참조가 설정됐어요',
            '인증 토큰이 승인되지 않은 주소로 함께 전송돼요. 그 주소가 다른 사람의 서버라면 토큰이 그대로 넘어가요.': '승인되지 않은 주소에 인증 참조가 설정돼 있어요. 실제 전송을 확인한 것은 아니지만 연결 시 자격증명이 노출될 수 있어요.',
            '토큰 ${n}개가 바뀐 주소로 보내지고 있어요': '미승인 주소의 자격증명 참조 설정 ${n}건',
            '같은 장치에서 실행되는': '명령 실행 방식으로 설정된',
            '인터넷 주소로 연결하는': '주소가 설정된',
        },
        'src/components/structure.tsx': {'어디서 실행되나': '어디에 선언됐나'},
    }
    patches = []
    for relative, substitutions in changes.items():
        original = (SOURCE/relative).read_text(encoding='utf-8')
        revised = original
        for old, new in substitutions.items():
            assert old in revised, (relative, old)
            revised = revised.replace(old, new)
        (DEST/relative).write_text(revised, encoding='utf-8')
        patches.extend(difflib.unified_diff(original.splitlines(True), revised.splitlines(True),
                         fromfile='a/dashboard/'+relative, tofile='b/dashboard/'+relative))
    PATCH.parent.mkdir(parents=True, exist_ok=True)
    PATCH.write_text(''.join(patches), encoding='utf-8')
    print('Prepared 2-file wording patch and isolated reviewed dashboard')


if __name__ == '__main__': main()
