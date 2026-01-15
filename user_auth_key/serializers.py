from rest_framework import serializers
from .models import UserKeyPair

class UserKeyPairSerializer(serializers.ModelSerializer):
    public_key = serializers.CharField(read_only=True)
    masked_private_key = serializers.SerializerMethodField()

    class Meta:
        model = UserKeyPair
        fields = ['public_key', 'masked_private_key', 'created_at', 'revoked']

    def get_masked_private_key(self, obj):
        return obj.masked_private_key
