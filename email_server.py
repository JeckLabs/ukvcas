import asyncio
import email
from aiosmtpd.controller import Controller
from aiohttp import web

email_handler = None

async def http_handle(request):
    return web.Response(text=email_handler.last_msg)


class EmailHandler:
    last_msg = ""

    async def handle_DATA(self, server, session, envelope):
        try:
            peer = session.peer
            mail_from = envelope.mail_from
            rcpt_tos = envelope.rcpt_tos
            data = envelope.content
            msg = email.message_from_bytes(data)
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    typ = part.get_content_type()
                    disp = str(part.get("Content-Disposition"))
                    charset = part.get_content_charset()
                    if not charset:
                        charset = 'latin1'
                    if typ == 'text/plain' and 'attachment' not in disp:
                        body = part.get_payload(decode=True).decode(encoding=charset, errors="ignore")
                        break
                    elif typ == 'text/html' and 'attachment' not in disp:                                
                        body = part.get_payload(decode=True).decode(encoding=charset, errors="ignore")
                        break
            else:               
                charset = msg.get_content_charset()
                if not charset:
                    charset = 'latin1'
                body = msg.get_payload(decode=True).decode(encoding=charset, errors="ignore")
        except:
            return '500 Could not process your message'
        else:
            self.last_msg = body

        return '250 OK'

if __name__ == '__main__':
    email_handler = EmailHandler()
    controller = Controller(email_handler, hostname='0.0.0.0', port=25)
    # Run the event loop in a separate thread.
    controller.start()
    app = web.Application()
    app.add_routes([web.get('/', http_handle)])
    web.run_app(app, host='0.0.0.0', port=666)
