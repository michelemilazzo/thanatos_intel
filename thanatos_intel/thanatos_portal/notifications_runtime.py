def send_notifications(case_name, requests):
    notifications=[]
    for req in requests:
        notifications.append({
            'case':case_name,
            'message':f"Document required: {req['document']}",
            'status':'queued'
        })

    return {
        'case':case_name,
        'notifications_created':len(notifications),
        'notifications':notifications,
        'next_step':'ocr_runtime'
    }
