from django.db.models import Prefetch
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import SimpleRateThrottle
from .models import StoreProfile, StorePhoto
from . import dinner


class StorePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = StorePhoto
        fields = ['id', 'image', 'caption', 'alt_text']


class StoreProfileSerializer(serializers.ModelSerializer):
    opening_hours = serializers.SerializerMethodField()

    def get_opening_hours(self, obj):
        from .pickup import opening_text
        return opening_text(obj)
    photos = StorePhotoSerializer(source='live_photos', many=True, read_only=True)

    class Meta:
        model = StoreProfile
        fields = ['name', 'description', 'address', 'opening_hours', 'phone', 'telegram_url',
                  'vk_url', 'instagram_url', 'email', 'map_url', 'map_embed_url', 'photos']


class StoreProfileView(APIView):
    def get(self, request):
        profile = StoreProfile.objects.prefetch_related(Prefetch('photos',
            queryset=StorePhoto.objects.filter(is_active=True).exclude(image=''), to_attr='live_photos')).first()
        if not profile:
            profile = StoreProfile(address='Севастополь, Камышовое шоссе, 25')
            profile.live_photos = []
        return Response(StoreProfileSerializer(profile, context={'request': request}).data)


class PickupSlotsView(APIView):
    def get(self, request):
        from .pickup import slots
        response = Response(slots())
        response['Cache-Control'] = 'no-store'
        return response


class DinnerThrottle(SimpleRateThrottle):
    scope = 'dinner'
    rate = '30/min'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class DinnerSchemaView(APIView):
    def get(self, request):
        return Response(dinner.schema())


class DinnerSuggestionsView(APIView):
    throttle_classes = [DinnerThrottle]

    def post(self, request):
        form = dinner.DinnerAnswers(data=request.data)
        form.is_valid(raise_exception=True)
        return Response({'results': dinner.suggestions(form.validated_data, request)})


class DinnerPrepareView(APIView):
    throttle_classes = [DinnerThrottle]

    def post(self, request):
        form = dinner.DinnerPreparation(data=request.data)
        form.is_valid(raise_exception=True)
        return Response(dinner.prepare_shopping(form.validated_data, request))
