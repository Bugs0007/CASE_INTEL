"""
Integration tests for the REST API views.

Uses Django's test client to verify endpoint routing, request
validation, and response structure. External services (LLM, embeddings)
are mocked.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Case, Conversation, Document, Message


class TestCaseAPI(TestCase):
    """Tests for /api/cases/ endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.case = Case.objects.create(
            case_number="CASE-001",
            title="Test Case",
            client_name="Test Client",
            case_type="civil",
            status="open",
        )

    def test_list_cases(self):
        response = self.client.get("/api/cases/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["case_number"], "CASE-001")

    def test_create_case(self):
        data = {
            "case_number": "CASE-002",
            "title": "New Case",
            "client_name": "New Client",
        }
        response = self.client.post("/api/cases/", data, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Case.objects.count(), 2)

    def test_retrieve_case(self):
        response = self.client.get(f"/api/cases/{self.case.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Test Case")

    def test_update_case(self):
        response = self.client.patch(
            f"/api/cases/{self.case.id}/",
            {"status": "closed"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, "closed")

    def test_delete_case(self):
        response = self.client.delete(f"/api/cases/{self.case.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Case.objects.count(), 0)


class TestConversationAPI(TestCase):
    """Tests for /api/conversations/ endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.case = Case.objects.create(
            case_number="CASE-001",
            title="Test Case",
            client_name="Test Client",
        )
        self.conversation = Conversation.objects.create(
            case=self.case,
            title="Test Conversation",
        )
        Message.objects.create(
            conversation=self.conversation,
            role="user",
            content="Hello",
        )

    def test_list_conversations(self):
        response = self.client.get("/api/conversations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_filter_conversations_by_case(self):
        response = self.client.get(f"/api/conversations/?case_id={self.case.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_retrieve_conversation_with_messages(self):
        response = self.client.get(f"/api/conversations/{self.conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["messages"]), 1)

    def test_delete_conversation(self):
        response = self.client.delete(f"/api/conversations/{self.conversation.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Conversation.objects.count(), 0)


class TestDocumentAPI(TestCase):
    """Tests for /api/documents/ endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.case = Case.objects.create(
            case_number="CASE-001",
            title="Test Case",
            client_name="Test Client",
        )
        self.document = Document.objects.create(
            case=self.case,
            filename="test.pdf",
            file_path="/tmp/test.pdf",
            file_type="pdf",
            processing_status="pending",
        )

    def test_list_documents(self):
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_filter_documents_by_case(self):
        response = self.client.get(f"/api/documents/?case_id={self.case.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_retrieve_document(self):
        response = self.client.get(f"/api/documents/{self.document.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["filename"], "test.pdf")

    def test_delete_document(self):
        response = self.client.delete(f"/api/documents/{self.document.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Document.objects.count(), 0)


class TestChatAPI(TestCase):
    """Tests for /api/chat/ endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.case = Case.objects.create(
            case_number="CASE-001",
            title="Test Case",
            client_name="Test Client",
        )

    def test_chat_rejects_empty_query(self):
        response = self.client.post("/api/chat/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_chat_rejects_nonexistent_case(self):
        response = self.client.post(
            "/api/chat/",
            {"query": "What is the motion about?", "case_id": 99999},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    @patch("core.views._ai_service")
    def test_chat_returns_response(self, mock_service):
        from core.services.ai_workflow import AIResponse

        mock_service.process_query.return_value = AIResponse(
            answer="The motion argues for dismissal.",
            confidence=0.85,
            citations=[],
            query_type="simple_qa",
            requires_clarification=False,
            clarification_question=None,
            message_id=1,
        )

        # Create a message for the conversation_id lookup
        conv = Conversation.objects.create(case=self.case, title="test")
        msg = Message.objects.create(conversation=conv, role="assistant", content="test")
        mock_service.process_query.return_value = AIResponse(
            answer="The motion argues for dismissal.",
            confidence=0.85,
            citations=[],
            query_type="simple_qa",
            requires_clarification=False,
            clarification_question=None,
            message_id=msg.id,
        )

        response = self.client.post(
            "/api/chat/",
            {"query": "What is the motion about?", "case_id": self.case.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("answer", response.data)
        self.assertEqual(response.data["answer"], "The motion argues for dismissal.")
