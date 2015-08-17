import httplib as http

from modularodm import Q

from framework.auth.decorators import must_be_logged_in
from framework.exceptions import HTTPError, PermissionsError
from framework import status
from framework.flask import redirect

from website.tokens.exceptions import UnsupportedSanctionHandlerKind, TokenError

def registration_approval_handler(action, registration, registered_from):
    status.push_status_message({
        'approve': 'Your Registration approval has been accepted.',
        'reject': 'Your disapproval has been accepted and the registration has been cancelled.',
    }[action], kind='success', trust=False)
    if action == 'approve':
        return redirect(registration.web_url_for('view_project'))
    else:
        return redirect(registered_from.web_url_for('view_project'))

def embargo_handler(action, registration, registered_from):
    status.push_status_message({
        'approve': 'Your Embargo approval has been accepted.',
        'reject': 'Your disapproval has been accepted and the embargo has been cancelled.',
    }[action], kind='success', trust=False)
    if action == 'approve':
        return redirect(registration.web_url_for('view_project'))
    else:
        return redirect(registered_from.web_url_for('view_project'))

def retraction_handler(action, registration, registered_from):
    status.push_status_message({
        'approve': 'Your Retraction approval has been accepted.',
        'reject': 'Your disapproval has been accepted and the retraction has been cancelled.'
    }[action], kind='success', trust=False)
    if action == 'approve':
        return redirect(registered_from.registered_from.web_url_for('view_project'))
    elif action == 'reject':
        return redirect(registration.web_url_for('view_project'))

SANCTION_HANDLERS = {
    'registration': registration_approval_handler,
    'embargo': embargo_handler,
    'retraction': retraction_handler,
}

@must_be_logged_in
def sanction_handler(kind, action, payload, encoded_token, auth, **kwargs):
    from website.models import Node, RegistrationApproval, Embargo, Retraction

    Model = None

    if kind == 'registration':
        Model = RegistrationApproval
    elif kind == 'embargo':
        Model = Embargo
    elif kind == 'retraction':
        Model = Retraction
    else:
        raise UnsupportedSanctionHandlerKind

    sanction_id = payload.get('sanction_id', None)
    sanction = Model.load(sanction_id)
    if sanction.is_rejected:
        raise HTTPError(http.GONE, data=dict(
            message_long="This registration has been rejected"
        ))
    do_action = getattr(sanction, action, None)
    if do_action:
        registration = Node.find_one(Q(sanction.SHORT_NAME, 'eq', sanction))
        registered_from = registration.registered_from
        try:
            do_action(auth.user, encoded_token)
        except TokenError as e:
            raise HTTPError(http.BAD_REQUEST, data={
                'message_short': e.message_short,
                'message_long': e.message_long
            })
        except PermissionsError as e:
            raise HTTPError(http.BAD_REQUEST, data={
                'message_short': 'Unauthorized access',
                'message_long': e.message
            })
        sanction.save()
        return SANCTION_HANDLERS[kind](action, registration, registered_from)
