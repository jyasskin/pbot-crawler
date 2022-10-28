import json
import logging
from collections.abc import Set
from typing import cast

from python_http_client.client import Response
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (Asm, Content, From, GroupId, Mail,
                                   Personalization, Subject, To)

logger = logging.getLogger(__name__)


class SendGrid:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.sg = SendGridAPIClient(api_key)
        self.client = self.sg.client

    def remove_unsubscribed(self) -> list[str]:
        """Removes unsubscribed subscribers from all lists.

        Returns: the list of unsubscribed emails, since contact deletion is
        asynchronous and might not have finished by the next step of sending
        emails.
        """
        response = cast(Response, self.client.suppression.unsubscribes.get())
        suppressed_emails: list[str] = [
            result["email"] for result in json.loads(response.body)
        ]
        if len(suppressed_emails) == 0:
            return []
        response = cast(
            Response,
            self.client.marketing.contacts.search.emails.post(
                request_body={"emails": suppressed_emails}
            ),
        )
        suppressed_contacts = json.loads(response.body)
        suppressed_contacts = suppressed_contacts["result"]
        self.client.marketing.contacts.delete(
            query_params={
                "ids": ",".join(contact["contact"]["id"] for contact in suppressed_contacts.values())
            }
        )
        logger.info("Removed %s unsubscribed contacts", len(suppressed_contacts))
        for email in suppressed_emails:
            self.client.asm.suppressions._("global")._(email).delete()
        return suppressed_emails

    def get_pbot_subscribers(self, exclude: Set[str] = frozenset()) -> list:
        response = cast(
            Response,
            self.client.marketing.contacts.search.post(
                request_body={
                    "query": "CONTAINS(list_ids, 'aacbe0f7-c0e1-4698-9b46-d03fce64f779')"
                }
            ),
        )
        return [
            contact
            for contact in json.loads(response.body)["result"]
            if contact["email"] not in exclude
        ]

    def send_mail(
        self,
        *,
        to: list,
        sender_email: str,
        sender_name: str,
        subject: str,
        html_content: str,
        plain_content: str | None = None
    ) -> None:
        message = Mail()
        for contact in to:
            p = Personalization()
            p.tos = [To(email=contact["email"])]
            message.add_personalization(p)
        message.subject = Subject(subject)
        message.from_email = From(email=sender_email, name=sender_name)
        message.content = [
            Content(mime_type="text/html", content=html_content),
            Content(mime_type="text/plain", content=plain_content),
        ]
        #message.asm = Asm(
        #    group_id=GroupId(-1),
        #)
        self.sg.send(message)
