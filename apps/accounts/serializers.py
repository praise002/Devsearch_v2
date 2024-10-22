
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
# from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Otp, User


class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'username', 'email', 'password']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        # Use the custom user manager to create a user with the validated data
        user = User.objects.create_user(
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            password=validated_data['password']
        )
        return user
    
    def validate(self, attrs):
        first_name = attrs['first_name']
        last_name = attrs['last_name']
        
        if len(first_name.split()) > 1:
            raise serializers.ValidationError({'first_name': 'No spacing allowed'})
        
        if len(last_name.split()) > 1:
            raise serializers.ValidationError({'last_name': 'No spacing allowed'})

        return attrs

class SendOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    
    def validate_email(self, value):
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError({
                'error': 'User with this email does not exist.'
            })
        
        return value

class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.IntegerField()
    
    def validate(self, attrs):
        email = attrs.get('email')
        otp = attrs.get('otp')
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({
                'error': 'User with this email does not exist.'
            })
        
        try:
            otp_record = Otp.objects.get(user=user, otp=otp)
        except Otp.DoesNotExist:
            raise serializers.ValidationError({
                'error': 'Invalid OTP provided.'
            })
        
        # Check if OTP is expired
        if not otp_record.is_valid:
            raise serializers.ValidationError({
                'error': 'OTP has expired.',
                'next_action': 'request_new_otp',  
                'request_url': '/api/v1/auth/send-otp/'
            })
        
        return attrs