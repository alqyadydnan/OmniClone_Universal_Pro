import sys
import os

# إضافة مسار المجلد الحالي
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# إضافة مجلد agent و protocol و engine
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# تشغيل الوكيل
from agent.main import run_agent

if __name__ == "__main__":
    run_agent()