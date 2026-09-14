"""真实端到端验证：跑一次完整 Agent 会话，证明不是演示品。

用法：
    cd backend && PYTHONPATH= python scripts/e2e_verify.py
"""
import sys
import os
import json

os.environ.setdefault('OPENHANDS_SUPPRESS_BANNER', '1')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops_pilot.server.settings import load_env  # noqa: E402

load_env()

from ops_pilot.server import db  # noqa: E402
from ops_pilot.runtime.runner import ConversationRunner  # noqa: E402

REQUEST = (
    "请巡检 jzz-18 主机的健康状态：报告 CPU、内存、磁盘、负载四个指标。"
    "必须真实调用只读工具采集，报告里要写明调用了哪些工具、返回的具体数值。"
)


def main() -> None:
    conn = db.connect('opspilot.db')
    runner = ConversationRunner(conn)
    print('LLM model :', runner.model)
    print('LLM base  :', runner.base_url)
    print('API key   :', 'SET' if runner.api_key else 'MISSING')
    print('=' * 70)

    task = runner.start_task(title='巡检 jzz-18', user_request=REQUEST, server_id='jzz-18')
    print('task_id:', task['id'])

    try:
        res = runner.run(task['id'], user_request=REQUEST, server_id='jzz-18')
        print('RESULT:', json.dumps(res, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        print('RUN ERROR:', type(exc).__name__, exc)
        import traceback
        traceback.print_exc()

    print('=' * 70)
    print('事件流（时间正序）:')
    for ev in reversed(runner.events(task['id'], limit=80)):
        print(f"  [{ev.get('kind')}] {ev.get('state')} | {str(ev.get('message'))[:300]}")


if __name__ == '__main__':
    main()
