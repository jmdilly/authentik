"""Flow Stage API Views"""
from typing import Iterable

from drf_yasg.utils import swagger_auto_schema
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.fields import BooleanField
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer, SerializerMethodField
from rest_framework.viewsets import GenericViewSet
from structlog.stdlib import get_logger

from authentik.core.api.utils import MetaNameSerializer, TypeCreateSerializer
from authentik.core.types import UserSettingSerializer
from authentik.flows.api.flows import FlowSerializer
from authentik.flows.models import Stage
from authentik.lib.utils.reflection import all_subclasses

LOGGER = get_logger()


class StageUserSettingSerializer(UserSettingSerializer):
    """User settings but can include a configure flow"""

    configure_flow = BooleanField(required=False)


class StageSerializer(ModelSerializer, MetaNameSerializer):
    """Stage Serializer"""

    component = SerializerMethodField()
    flow_set = FlowSerializer(many=True, required=False)

    def get_component(self, obj: Stage) -> str:
        """Get object type so that we know how to edit the object"""
        # pyright: reportGeneralTypeIssues=false
        if obj.__class__ == Stage:
            return ""
        return obj.component

    class Meta:

        model = Stage
        fields = [
            "pk",
            "name",
            "component",
            "verbose_name",
            "verbose_name_plural",
            "flow_set",
        ]


class StageViewSet(
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    """Stage Viewset"""

    queryset = Stage.objects.all().select_related("flow_set")
    serializer_class = StageSerializer
    search_fields = ["name"]
    filterset_fields = ["name"]

    def get_queryset(self):
        return Stage.objects.select_subclasses()

    @swagger_auto_schema(responses={200: TypeCreateSerializer(many=True)})
    @action(detail=False, pagination_class=None, filter_backends=[])
    def types(self, request: Request) -> Response:
        """Get all creatable stage types"""
        data = []
        for subclass in all_subclasses(self.queryset.model, False):
            subclass: Stage
            data.append(
                {
                    "name": subclass._meta.verbose_name,
                    "description": subclass.__doc__,
                    "component": subclass().component,
                    "model_name": subclass._meta.model_name
                }
            )
        data = sorted(data, key=lambda x: x["name"])
        return Response(TypeCreateSerializer(data, many=True).data)

    @swagger_auto_schema(responses={200: StageUserSettingSerializer(many=True)})
    @action(detail=False, pagination_class=None, filter_backends=[])
    def user_settings(self, request: Request) -> Response:
        """Get all stages the user can configure"""
        _all_stages: Iterable[Stage] = Stage.objects.all().select_subclasses()
        matching_stages: list[dict] = []
        for stage in _all_stages:
            user_settings = stage.ui_user_settings
            if not user_settings:
                continue
            user_settings.initial_data["object_uid"] = str(stage.pk)
            if hasattr(stage, "configure_flow"):
                user_settings.initial_data["configure_flow"] = bool(
                    stage.configure_flow
                )
            if not user_settings.is_valid():
                LOGGER.warning(user_settings.errors)
            matching_stages.append(user_settings.initial_data)
        return Response(matching_stages)
