import mmap
import os
import gc
import psutil

class MemoryOptimizer:
    """
    محسن الذاكرة الواقعي لـ Odysseus.
    يركز على الاستخدام الفعلي للموارد المتاحة في Hugging Face Spaces.
    """
    def __init__(self):
        self.mapped_files = {}
        try:
            self.process = psutil.Process(os.getpid())
        except:
            self.process = None

    def smart_load(self, file_path):
        """تحميل الملفات الكبيرة باستخدام mmap بدلاً من قراءتها بالكامل في الرام"""
        if not os.path.exists(file_path):
            return None
        
        try:
            f = open(file_path, "r+b")
            mm = mmap.mmap(f.fileno(), 0)
            self.active_mappings[file_path] = (f, mm)
            return mm
        except Exception as e:
            print(f"Error mapping file {file_path}: {e}")
            return None

    def force_cleanup(self):
        """تنظيف الرام القسري"""
        gc.collect()
        for path, (f, mm) in list(self.mapped_files.items()):
            try:
                mm.close()
                f.close()
            except:
                pass
            del self.mapped_files[path]
        return "Memory Purged and Optimized"

    def get_ram_usage_stats(self):
        """إحصائيات واقعية لاستخدام الذاكرة (Reality Audit)."""
        if not self.process:
            return {"status": "Unknown"}
            
        mem = self.process.memory_info()
        rss_gb = mem.rss / (1024**3)
        
        # Hugging Face Spaces limit is typically 16GB
        limit_gb = 16.0
        usage_percent = (rss_gb / limit_gb) * 100
        
        return {
            "physical_usage_gb": round(rss_gb, 2),
            "usage_percent": f"{round(usage_percent, 1)}%",
            "limit_gb": limit_gb,
            "status": "Healthy" if usage_percent < 80 else "Critical",
            "mapped_files": len(self.mapped_files)
        }

memory_optimizer = MemoryOptimizer()
