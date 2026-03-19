# courriers/notify.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()

def notify_user(user_id, message, notification_type='notification', data=None):
    if not user_id:
        return

    try:
        async_to_sync(channel_layer.group_send)(
            f'user_{user_id}',
            {
                'type': 'send_notification',
                'notification_type': notification_type,
                'message': message,
                'data': data or {},
            }
        )
    except Exception as e:
        print(f'[notify_user] Erreur envoi notification user {user_id}: {e}')

def notify_users(user_ids, message, notification_type='notification', data=None):
    for uid in (user_ids or []):
        notify_user(uid, message, notification_type, data)

def notify_service(service_id, message, notification_type='notification', data=None):
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user_ids = User.objects.filter(
            service_id=service_id, actif=True
        ).values_list('id', flat=True)
        notify_users(list(user_ids), message, notification_type, data)
    except Exception as e:
        print(f'[notify_service] Erreur: {e}')