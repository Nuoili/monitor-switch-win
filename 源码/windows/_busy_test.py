# -*- coding: utf-8 -*-
"""回归测试：do_switch 连续调用后 busy 必须复位（旧版只在失败分支复位）。"""
import monitor_switch_gui as m

calls = []

def fake_ok(v):
    calls.append(("ok", v))
    return True

def fake_fail(v):
    calls.append(("fail", v))
    return False

a = m.App()
a.hwnd = 0
a.busy = False

m.set_input = fake_ok
for i in range(3):
    a.do_switch(m.INPUT_HDMI1 if i % 2 == 0 else m.INPUT_DP, "SRC%d" % i)
    print("after call %d -> busy=%s ok_calls=%d" % (i + 1, a.busy, len(calls)))
    assert a.busy is False, "busy 没复位，第 %d 次之后就会没反应" % (i + 1)

# 失败路径也不能卡住（会弹 MessageBox，测试里屏蔽掉）
m.user32.MessageBoxW = lambda *args: 0
m.set_input = fake_fail
m.time.sleep = lambda s: None
a.do_switch(m.INPUT_DP, "FAIL")
print("after fail -> busy=%s" % a.busy)
assert a.busy is False

# 缓存句柄失效要能自愈：塞一个假句柄，_probe 会失败，必须重新枚举
m._cached[0] = 1111
h1 = m._handle()
print("stale cache 1111 -> handle=%s cache=%s" % (h1, m._cached[0]))
assert h1 and h1 != 1111, "失效缓存没被丢弃"
assert m._cached[0] == h1, "新句柄没写回缓存"

# 缓存有效时直接复用，不重新枚举
before = h1
h2 = m._handle()
print("valid cache -> handle=%s" % h2)
assert h2 == before, "有效缓存被无谓丢弃"
print("ALL PASS")
