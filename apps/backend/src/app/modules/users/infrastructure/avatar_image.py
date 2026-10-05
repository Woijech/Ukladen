import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.modules.users.domain.avatar import (
    AVATAR_CONTENT_TYPES,
    AVATAR_SIZE,
    MAX_AVATAR_BYTES,
    MAX_AVATAR_PIXELS,
    AvatarTooLarge,
    InvalidAvatar,
)


class PillowAvatarImageProcessor:
    def normalize(self, content: bytes, content_type: str) -> bytes:
        if len(content) > MAX_AVATAR_BYTES:
            raise AvatarTooLarge()
        expected_format = AVATAR_CONTENT_TYPES.get(content_type)
        if not content or expected_format is None:
            raise InvalidAvatar()
        try:
            with warnings.catch_warnings(action="error", category=Image.DecompressionBombWarning):
                with Image.open(BytesIO(content), formats=[expected_format]) as image:
                    if image.width * image.height > MAX_AVATAR_PIXELS:
                        raise AvatarTooLarge()
                    if getattr(image, "n_frames", 1) != 1:
                        raise InvalidAvatar()
                    image.verify()
            with Image.open(BytesIO(content), formats=[expected_format]) as image:
                image.load()
                oriented = ImageOps.exif_transpose(image)
                resized = ImageOps.fit(oriented.convert("RGBA"), (AVATAR_SIZE, AVATAR_SIZE))
                # Copy pixels into a new image so input EXIF, ICC and text cannot survive.
                clean = Image.new("RGBA", resized.size)
                clean.paste(resized)
                output = BytesIO()
                clean.save(output, format="PNG")
                return output.getvalue()
        except Image.DecompressionBombError, Image.DecompressionBombWarning:
            raise AvatarTooLarge() from None
        except InvalidAvatar:
            raise
        except UnidentifiedImageError, OSError, SyntaxError, ValueError:
            raise InvalidAvatar() from None
