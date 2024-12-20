from django.http import Http404
from rest_framework.exceptions import ValidationError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.filters import SearchFilter

from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import OpenApiResponse, OpenApiParameter


from apps.accounts.validators import validate_uuid
from apps.common.pagination import CustomPagination
from apps.common.serializers import (
    ErrorDataResponseSerializer,
    ErrorResponseSerializer,
    SuccessResponseSerializer,
)
from apps.profiles.models import Profile
from .models import Message
from .serializers import MessageSerializer

tags = ["Messages"]


# View for listing inbox messages
class InboxView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = MessageSerializer
    paginator_class = CustomPagination()
    paginator_class.page_size = 10

    @extend_schema(
        summary="Retrieve user's inbox messages",
        description="This endpoint allows authenticated users to view their inbox messages. It returns a list of messages received by the user. Additionally, it provides a count of unread messages to indicate any new notifications in the user's inbox.",
        tags=tags,
        responses={
            200: OpenApiResponse(
                description="Successfully retrieved inbox messages and unread count",
                response=SuccessResponseSerializer,
            ),
            401: OpenApiResponse(
                description="Unauthorized access - user must be authenticated",
                response=ErrorResponseSerializer,
            ),
        },
    )
    def get(self, request):
        messages = Message.objects.filter(recipient=request.user.profile)
        paginated_projects = self.paginator_class.paginate_queryset(messages, request)

        serializer = self.serializer_class(messages, many=True)

        unread_count = messages.filter(is_read=False).count()

        return Response(
            {
                "count": messages.count(),
                "next": paginated_projects.get("next"),
                "previous": paginated_projects.get("previous"),
                "results": serializer.data,
                "unread_count": unread_count,
                "per_page": paginated_projects.get("per_page"),
                "current_page": paginated_projects.get("current_page"),
                "last_page": paginated_projects.get("last_page"),
            },
            status=status.HTTP_200_OK,
        )


class InboxGenericView(ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = MessageSerializer
    pagination_class = CustomPagination
    filter_backends = [SearchFilter]
    search_fields = ["subject", "body"]

    @extend_schema(
        summary="Retrieve user's inbox messages",
        description=(
            "This endpoint allows authenticated users to view their inbox messages. "
            "It supports filtering messages using a search term. Additionally, it provides "
            "a count of unread messages."
        ),
        parameters=[
            OpenApiParameter(
                name="search",
                description="Search messages by (e.g., subject or body).",
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Successfully retrieved inbox messages and unread count",
                response=SuccessResponseSerializer,
            ),
            401: OpenApiResponse(
                description="Unauthorized access - user must be authenticated",
                response=ErrorResponseSerializer,
            ),
        },
        tags=tags,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """
        Return the filtered queryset of messages for the authenticated user.
        """
        return Message.objects.filter(recipient=self.request.user.profile)

    def list(self, request, *args, **kwargs):
        """
        Override the default list method to include unread_count in the response.
        """
        queryset = self.filter_queryset(self.get_queryset())  # Apply filters
        page = self.paginate_queryset(queryset)

        unread_count = self.get_queryset().filter(is_read=False).count()  # Unread count

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                {
                    "results": serializer.data,
                    "unread_count": unread_count,
                }
            )

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "results": serializer.data,
                "unread_count": unread_count,
            }
        )


# View for viewing a specific message
class ViewMessage(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = MessageSerializer

    @extend_schema(
        summary="Retrieve a specific message",
        description="This endpoint allows an authenticated user to retrieve the details of a specific message by ID. If the message is unread, it will automatically be marked as read upon retrieval.",
        tags=tags,
        responses={
            200: OpenApiResponse(
                response=SuccessResponseSerializer,
                description="Successfully retrieved the message details.",
            ),
            404: OpenApiResponse(
                description="Message not found or invalid message ID.",
                response=ErrorResponseSerializer,
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided or invalid.",
            ),
        },
    )
    def get(self, request, id):
        if not validate_uuid(id):
            raise Http404("Invalid message ID")

        try:
            message = request.user.profile.messages.select_related(
                "sender__user", "recipient"
            ).get(id=id)
        except Message.DoesNotExist:
            return Response(
                {"error": "Message not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.serializer_class(message)

        # Mark the message as read if it's currently unread
        if not message.is_read:
            message.is_read = True
            message.save()

        return Response(serializer.data, status=status.HTTP_200_OK)


# View for creating a new message
class CreateMessage(APIView):
    serializer_class = MessageSerializer

    @extend_schema(
        summary="Send a message to a specific user",
        description="This endpoint allows an anyone to send a message to a specific recipient by their profile ID. The sender's profile is automatically associated with the message if they are logged in. Users cannot message themselves.",
        tags=tags,
        responses={
            201: OpenApiResponse(
                response=SuccessResponseSerializer,
                description="Message successfully created and sent.",
            ),
            400: OpenApiResponse(
                description="Bad request - validation error.",
                response=ErrorDataResponseSerializer,
            ),
            404: OpenApiResponse(
                description="Recipient profile not found or invalid profile ID.",
                response=ErrorResponseSerializer,
            ),
        },
    )
    def post(self, request, profile_id):
        if not validate_uuid(profile_id):
            raise Http404("Invalid profile id")

        try:
            recipient = Profile.objects.get(id=profile_id)
        except Profile.DoesNotExist:
            raise Http404("Profile not found.")

        # try:
        #     sender = request.user.profile
        # except:
        #     sender = None

        sender = request.user.profile if request.user.is_authenticated else None

        # Prevent users from messaging themselves
        if sender and sender.id == recipient.id:
            raise ValidationError("You cannot message yourself.")

        data = request.data.copy()

        data["recipient"] = recipient.id

        serializer = self.serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(sender=sender)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


# View for deleting a message
class DeleteMessage(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Delete a specific message",
        description="This endpoint allows an authenticated user to delete a specific message they received. The message ID must be valid, and the message must belong to the authenticated user. Upon successful deletion, a confirmation message is returned.",
        tags=tags,
        responses={
            204: OpenApiResponse(
                description="Message deleted successfully.",
                response=SuccessResponseSerializer,
            ),
            404: OpenApiResponse(
                description="Message not found or invalid message ID.",
                response=ErrorResponseSerializer,
            ),
            401: OpenApiResponse(
                description="Authentication credentials were not provided.",
                response=ErrorResponseSerializer,
            ),
        },
    )
    def delete(self, request, message_id):
        if not validate_uuid(message_id):
            raise Http404("Invalid message id")

        try:
            message = Message.objects.get(id=message_id, recipient=request.user.profile)
        except Message.DoesNotExist:
            raise Http404("Message not found.")

        message.delete()
        return Response(
            {"message": "Message deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )
