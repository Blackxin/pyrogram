# Pyrogram - Telegram MTProto API Client Library for Python
# Copyright (C) 2017-2019 Dan Tès <https://github.com/delivrance>
#
# This file is part of Pyrogram.
#
# Pyrogram is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Pyrogram is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Pyrogram.  If not, see <http://www.gnu.org/licenses/>.

import binascii
import struct
from threading import Event
from typing import Union

import pyrogram
from pyrogram.client.ext import BaseClient, utils
from pyrogram.errors import FileIdInvalid


class DownloadMedia(BaseClient):
    def download_media(
        self,
        message: Union["pyrogram.Message", str],
        file_name: str = "",
        block: bool = True,
        progress: callable = None,
        progress_args: tuple = ()
    ) -> Union[str, None]:
        """Download the media from a message.

        Parameters:
            message (:obj:`Message` | ``str``):
                Pass a Message containing the media, the media itself (message.audio, message.video, ...) or
                the file id as string.

            file_name (``str``, *optional*):
                A custom *file_name* to be used instead of the one provided by Telegram.
                By default, all files are downloaded in the *downloads* folder in your working directory.
                You can also specify a path for downloading files in a custom location: paths that end with "/"
                are considered directories. All non-existent folders will be created automatically.

            block (``bool``, *optional*):
                Blocks the code execution until the file has been downloaded.
                Defaults to True.

            progress (``callable``):
                Pass a callback function to view the download progress.
                The function must take *(client, current, total, \*args)* as positional arguments (look at the section
                below for a detailed description).

            progress_args (``tuple``):
                Extra custom arguments for the progress callback function. Useful, for example, if you want to pass
                a chat_id and a message_id in order to edit a message with the updated progress.

        Other Parameters:
            client (:obj:`Client`):
                The Client itself, useful when you want to call other API methods inside the callback function.

            current (``int``):
                The amount of bytes downloaded so far.

            total (``int``):
                The size of the file.

            *args (``tuple``, *optional*):
                Extra custom arguments as defined in the *progress_args* parameter.
                You can either keep *\*args* or add every single extra argument in your function signature.

        Returns:
            ``str`` | ``None``: On success, the absolute path of the downloaded file is returned, otherwise, in case
            the download failed or was deliberately stopped with :meth:`~Client.stop_transmission`, None is returned.

        Raises:
            RPCError: In case of a Telegram RPC error.
            ``ValueError`` if the message doesn't contain any downloadable media
        """
        error_message = "This message doesn't contain any downloadable media"
        available_media = ("audio", "document", "photo", "sticker", "animation", "video", "voice", "video_note")

        file_size = None
        mime_type = None
        date = None

        if isinstance(message, pyrogram.Message):
            for kind in available_media:
                media = getattr(message, kind, None)

                if media is not None:
                    break
            else:
                raise ValueError(error_message)
        else:
            media = message

        if isinstance(media, str):
            file_id_str = media
        else:
            file_id_str = media.file_id
            file_name = getattr(media, "file_name", "")
            file_size = getattr(media, "file_size", None)
            mime_type = getattr(media, "mime_type", None)
            date = getattr(media, "date", None)

        data = self.FileData(
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            date=date
        )

        def get_existing_attributes() -> dict:
            return dict(filter(lambda x: x[1] is not None, data._asdict().items()))

        try:
            decoded = utils.decode(file_id_str)
            media_type = decoded[0]

            if media_type == 1:
                unpacked = struct.unpack("<iiqqib", decoded)
                dc_id, peer_id, volume_id, local_id, is_big = unpacked[1:]

                data = self.FileData(
                    **get_existing_attributes(),
                    media_type=media_type,
                    dc_id=dc_id,
                    peer_id=peer_id,
                    volume_id=volume_id,
                    local_id=local_id,
                    is_big=bool(is_big)
                )
            elif media_type in (0, 2, 14):
                unpacked = struct.unpack("<iiqqc", decoded)
                dc_id, file_id, access_hash, thumb_size = unpacked[1:]

                data = self.FileData(
                    **get_existing_attributes(),
                    media_type=media_type,
                    dc_id=dc_id,
                    file_id=file_id,
                    access_hash=access_hash,
                    thumb_size=thumb_size.decode()
                )
            elif media_type in (3, 4, 5, 8, 9, 10, 13):
                unpacked = struct.unpack("<iiqq", decoded)
                dc_id, file_id, access_hash = unpacked[1:]

                data = self.FileData(
                    **get_existing_attributes(),
                    media_type=media_type,
                    dc_id=dc_id,
                    file_id=file_id,
                    access_hash=access_hash
                )
            else:
                raise ValueError("Unknown media type: {}".format(file_id_str))
        except (AssertionError, binascii.Error, struct.error):
            raise FileIdInvalid from None

        done = Event()
        path = [None]

        self.download_queue.put((data, file_name, done, progress, progress_args, path))

        if block:
            done.wait()

        return path[0]
