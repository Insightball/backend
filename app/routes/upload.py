from fastapi import APIRouter, Depends, HTTPException
from datetime import timedelta
import boto3
from botocore.exceptions import ClientError
import uuid

from app.config import settings
from app.schemas import S3PresignedUrlRequest, S3PresignedUrlResponse
from app.models import User
from app.dependencies import get_current_active_user

router = APIRouter()

def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
        endpoint_url=f"https://s3.{settings.AWS_REGION}.amazonaws.com"
    )

@router.post("/presigned-url", response_model=S3PresignedUrlResponse)
async def get_presigned_upload_url(
    request: S3PresignedUrlRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Get a presigned URL for uploading a video to S3"""
    
    try:
        # Generate unique file key
        file_extension = request.filename.split('.')[-1]
        file_key = f"videos/{current_user.id}/{uuid.uuid4()}.{file_extension}"
        
        # Generate presigned URL (valid for 1 hour)
        presigned_url = get_s3_client().generate_presigned_url(
            'put_object',
            Params={
                'Bucket': settings.AWS_BUCKET_NAME,
                'Key': file_key,
                'ContentType': request.content_type
            },
            ExpiresIn=3600  # 1 hour
        )
        
        return S3PresignedUrlResponse(
            upload_url=presigned_url,
            file_key=file_key,
            expires_in=3600
        )
        
    except ClientError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating presigned URL: {str(e)}"
        )

@router.get("/download-url/{file_key:path}")
async def get_presigned_download_url(
    file_key: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get a presigned URL for downloading a file from S3"""
    
    try:
        # Verify user owns this file (file_key should start with videos/{user_id}/)
        if not file_key.startswith(f"videos/{current_user.id}/"):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this file"
            )
        
        # Generate presigned URL (valid for 1 hour)
        presigned_url = get_s3_client().generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_BUCKET_NAME,
                'Key': file_key
            },
            ExpiresIn=3600  # 1 hour
        )
        
        return {
            "download_url": presigned_url,
            "expires_in": 3600
        }
        
    except ClientError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating presigned URL: {str(e)}"
        )


@router.post("/presigned-url/image", response_model=S3PresignedUrlResponse)
async def get_presigned_image_url(
    request: S3PresignedUrlRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Get a presigned URL for uploading an image (logo, photo) to S3"""

    allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/svg+xml']
    if request.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Type de fichier non autorisé. Utilisez JPG, PNG, WEBP ou SVG.")

    try:
        file_extension = request.filename.split('.')[-1].lower()
        file_key = f"images/{current_user.id}/{uuid.uuid4()}.{file_extension}"

        presigned_url = get_s3_client().generate_presigned_url(
            'put_object',
            Params={
                'Bucket': settings.AWS_BUCKET_NAME,
                'Key': file_key,
                'ContentType': request.content_type,
            },
            ExpiresIn=900  # 15 min
        )

        return S3PresignedUrlResponse(
            upload_url=presigned_url,
            file_key=file_key,
            expires_in=900
        )

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Erreur S3 : {str(e)}")
