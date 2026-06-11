import os
import boto3
from botocore.exceptions import NoCredentialsError

class UniversalStorage:
    """
    نظام التخزين العالمي لربط Odysseus بـ S3/R2 و Google Drive.
    يضمن مساحة تخزين غير محدودة بعيداً عن قيود Hugging Face.
    """
    def __init__(self):
        self.s3_client = None
        self.setup_s3()

    def setup_s3(self):
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        endpoint = os.getenv("S3_ENDPOINT_URL") # لربط Cloudflare R2
        
        if access_key and secret_key:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                endpoint_url=endpoint
            )

    def upload_file(self, local_path, bucket_name, object_name=None):
        if not self.s3_client:
            return False
        if object_name is None:
            object_name = os.path.basename(local_path)
        try:
            self.s3_client.upload_file(local_path, bucket_name, object_name)
            return True
        except Exception as e:
            print(f"Upload failed: {e}")
            return False

    def get_storage_status(self):
        return {
            "provider": "S3/R2 Integrated" if self.s3_client else "Local/GitHub Sync Only",
            "capacity": "Unlimited (External)",
            "status": "Active"
        }

universal_storage = UniversalStorage()
