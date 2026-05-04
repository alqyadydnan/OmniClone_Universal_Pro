import sys
import os

# إضافة مسار المجلد الحالي
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# تشغيل البرنامج
from src.main import main

if __name__ == "__main__":
    main()