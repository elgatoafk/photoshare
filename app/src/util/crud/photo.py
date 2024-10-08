import base64
import io
from base64 import b64encode

from sqlalchemy import and_, func, desc
from sqlalchemy.orm import joinedload, selectinload
from io import BytesIO
from uuid import uuid4
import cloudinary
import cloudinary.uploader
import qrcode
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.src.config.config import settings
from app.src.config.logging_config import log_function
from app.src.util.crud.tag import parse_tags
from app.src.util.crud.user import get_user
from app.src.util.models.photo import Photo
from app.src.util.models.rating import Rating
from app.src.util.models.user import User
from tenacity import retry, wait_fixed, stop_after_attempt

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


class PhotoService:
    """
    A class that provides image-related services such as uploading, resizing, adding filters, and generating QR codes.
    """

    @staticmethod
    @log_function
    async def upload_photo(file):
        """Uploads an image to the cloud storage.

        """
        unique_filename = str(uuid4())
        public_id = f"f4aaafaf-7376-4506-976a-bae4d91b5e7c/{unique_filename}"
        r = cloudinary.uploader.upload(file.file, public_id=public_id, overwrite=True)
        src_url = cloudinary.CloudinaryImage(public_id).build_url(
            version=r.get("version")
        )
        return public_id, src_url

    @staticmethod
    @log_function
    async def resize_photo(
            public_id: str, width: int, height: int):
        """Resizes an image using Cloudinary API.

        """

        transformed_url = cloudinary.uploader.explicit(
            public_id,
            type="upload",
            eager=[
                {
                    "width": width,
                    "height": height,
                    "crop": "fill",
                    "gravity": "auto",
                },
                {"fetch_format": "auto"},
                {"radius": "max"},
            ],
        )
        try:
            url_to_return = transformed_url["eager"][0]["secure_url"]
        except KeyError:
            raise HTTPException(status_code=400, detail="Invalid width or height")
        return url_to_return

    @staticmethod
    @log_function
    async def add_filter(public_id: str, filter: str):
        """Apply a filter to an image and return the transformed URL.
        """

        effect = f"art:{filter}"
        transformed_url = cloudinary.uploader.explicit(
            public_id,
            type="upload",
            eager=[
                {
                    "effect": effect,
                },
                {"fetch_format": "auto"},
                {"radius": "max"},
            ],
        )
        print(transformed_url)
        if 'eager' in transformed_url and transformed_url['eager']:
            url_to_return = transformed_url["eager"][0].get("secure_url")
        else:
            raise HTTPException(status_code=400, detail="Invalid filter or transformation failed")
        return url_to_return

    @staticmethod
    @log_function
    async def generate_qr_code(photo_url: str) -> str:
        """Generates a QR code image from the given image URL and returns it as a base64 encoded string."""

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(photo_url)
        qr.make(fit=True)

        qr_code = qr.make_image(fill_color="black", back_color="white")

        qr_code_io = io.BytesIO()
        qr_code.save(qr_code_io)
        qr_code_io.seek(0)

        qr_code_base64 = base64.b64encode(qr_code_io.getvalue()).decode("utf-8")

        return qr_code_base64

@log_function
async def create_photo_in_db(description: str, file, user_id: int, db: AsyncSession, tag_names: list = []) -> Photo:
    """
        Creates a Photo record in the database and uploads the image to Cloudinary.

        Args:
            description (str): The description of the photo.
            file: The file object of the photo.
            user_id (int): The ID of the user who is uploading the photo.
            db (AsyncSession): The database session.
            tag_names (list): List of tag names associated with the photo.

        Returns:
            Photo: The created Photo object.
        """
    public_id, photo_url = await PhotoService.upload_photo(file)
    tag_instances = await parse_tags(db, tag_names, settings.MAX_TAGS)
    new_photo = Photo(
        description=description,
        url=photo_url,
        public_id=public_id,
        user_id=user_id,
        tags=tag_instances
    )
    db.add(new_photo)

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    if user:
        user.photos_uploaded = user.photos_uploaded + 1
        db.add(user)

    await db.commit()
    await db.refresh(new_photo)

    return new_photo


@log_function
async def get_photo(db: AsyncSession, photo_id: int):
    """
    Asynchronously retrieves a photo from the database by its ID.

    Parameters:
    - db (AsyncSession): The SQLAlchemy AsyncSession object for database operations.
    - photo_id (int): The unique identifier of the photo to retrieve.


    Returns:
    - PhotoResponse: A response object containing the photo's details.

    Raises:
    - HTTPException: If the photo is not found in the database, a 404 Not Found error is raised.
    - HTTPException: If an error occurs during database operations, a 500 Internal Server Error is raised.
    """

    result = await db.execute(select(Photo).filter(Photo.id == photo_id))
    db_photo = result.scalars().first()
    if not db_photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    return db_photo


@log_function
async def update_photo_description(photo_id: int, new_description: str, db: AsyncSession) -> Photo:
    """
    Updates the description of a photo in the database.

    Args:
        photo_id (int): The ID of the photo to update.
        new_description (str): The new description for the photo.
        db (AsyncSession): The database session.

    Returns:
        Photo: The updated Photo object.
    """
    photo = await get_photo(db, photo_id)
    photo.description = new_description
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


@log_function
async def delete_photo(db: AsyncSession, photo_id: int):
    """
    Deletes a photo from the database and decrements the owner's photo counter.

    Parameters:
    db (AsyncSession): The database session.
    photo_id (int): The ID of the photo to delete.

    Raises:
    HTTPException: If the photo is not found.
    """
    photo = await get_photo(db, photo_id)

    user = await get_user(db, photo.user_id)
    if user:
        user.photos_uploaded -= 1
        db.add(user)

    await db.delete(photo)
    await db.commit()


@log_function
async def update_photo_url(db: AsyncSession, photo_id: int, new_url: str, ) -> Photo:
    """
    Updates the URL of an existing Photo record in the database.

    Args:
        photo_id (int): The ID of the photo to update.
        new_url (str): The new URL of the photo.
        db (AsyncSession): The database session.
    Returns:
        Photo: The updated Photo object.
    """
    photo = await get_photo(db, photo_id)
    photo.url = new_url
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


@retry(wait=wait_fixed(1), stop=stop_after_attempt(3))
@log_function
async def get_photos_with_details(db: AsyncSession):
    result = await db.execute(
        select(Photo)
        .options(selectinload(Photo.tags), selectinload(Photo.owner))
        .order_by(desc(Photo.id))
    )
    photos_with_details = result.scalars().all()
    return photos_with_details


async def get_post_by_id(db: AsyncSession, photo_id: int) -> Photo:
    """
    Retrieve a photo by its ID, including related tags, comments, and the owner.
    Also calculates the average rating for the photo.

    Args:
        db (AsyncSession): The SQLAlchemy asynchronous session.
        photo_id (int): The unique identifier of the photo.

    Returns:
        Photo: The photo object with related tags, comments, owner, and average rating.
        None: If the photo is not found.
    """

    result = await db.execute(
        select(Photo)
        .options(selectinload(Photo.tags), selectinload(Photo.comments), selectinload(Photo.owner))
        .filter(Photo.id == photo_id)
        .outerjoin(Rating)
        .group_by(Photo.id)
        .add_columns(func.round(func.avg(Rating.rating), 2).label("average_rating"))
    )

    photo, average_rating = result.first() or (None, None)

    if photo:
        photo.average_rating = average_rating  # Attach the calculated average rating to the photo

    return photo
