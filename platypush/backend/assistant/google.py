"""
.. moduleauthor:: Fabio Manganiello <blacklight86@gmail.com>
.. license: MIT
"""

import json
import os
import subprocess
import time

import google.oauth2.credentials

from google.assistant.library import Assistant
from google.assistant.library.event import EventType, AlertType
from google.assistant.library.file_helpers import existing_file

from platypush.backend import Backend
from platypush.message.event.assistant import \
    ConversationStartEvent, ConversationEndEvent, ConversationTimeoutEvent, \
    ResponseEvent, NoResponseEvent, SpeechRecognizedEvent, AlarmStartedEvent, \
    AlarmEndEvent, TimerStartedEvent, TimerEndEvent, AlertStartedEvent, \
    AlertEndEvent


class AssistantGoogleBackend(Backend):
    """
    Google Assistant backend.

    It listens for voice commands and post conversation events on the bus.

    **WARNING**: This backend is deprecated, as the underlying Google Assistant
    library has been deprecated too: https://developers.google.com/assistant/sdk/reference/library/python/
    The old library might still work on some systems but its proper functioning
    is not guaranteed.
    Please use the Snowboy backend for hotword detection and the Google Assistant
    push-to-talk plugin for assistant interaction instead.

    Triggers:

        * :class:`platypush.message.event.assistant.ConversationStartEvent` \
            when a new conversation starts
        * :class:`platypush.message.event.assistant.SpeechRecognizedEvent` \
            when a new voice command is recognized
        * :class:`platypush.message.event.assistant.NoResponse` \
            when a conversation returned no response
        * :class:`platypush.message.event.assistant.ResponseEvent` \
            when the assistant is speaking a response
        * :class:`platypush.message.event.assistant.ConversationTimeoutEvent` \
            when a conversation times out
        * :class:`platypush.message.event.assistant.ConversationEndEvent` \
            when a new conversation ends
        * :class:`platypush.message.event.assistant.AlarmStartedEvent` \
            when an alarm starts
        * :class:`platypush.message.event.assistant.AlarmEndEvent` \
            when an alarm ends
        * :class:`platypush.message.event.assistant.TimerStartedEvent` \
            when a timer starts
        * :class:`platypush.message.event.assistant.TimerEndEvent` \
            when a timer ends

    Requires:

        * **google-assistant-library** (``pip install google-assistant-library``)
        * **google-assistant-sdk[samples]** (``pip install google-assistant-sdk[samples]``)
    """

    def __init__(self,
                 credentials_file=os.path.join(
                     os.path.expanduser('~/.config'),
                     'google-oauthlib-tool', 'credentials.json'),
                 device_model_id='Platypush', **kwargs):
        """
        :param credentials_file: Path to the Google OAuth credentials file \
            (default: ~/.config/google-oauthlib-tool/credentials.json). \
            See https://developers.google.com/assistant/sdk/guides/library/python/embed/install-sample#generate_credentials \
            for instructions to get your own credentials file.

        :type credentials_file: str

        :param device_model_id: Device model ID to use for the assistant \
            (default: Platypush)
        :type device_model_id: str
        """

        super().__init__(**kwargs)
        self.credentials_file = credentials_file
        self.device_model_id = device_model_id
        self.assistant = None
        self._has_error = False

        with open(self.credentials_file, 'r') as f:
            self.credentials = google.oauth2.credentials.Credentials(
                token=None,
                **json.load(f))

        self.logger.info('Initialized Google Assistant backend')

    def _process_event(self, event):
        self.logger.info('Received assistant event: {}'.format(event))
        self._has_error = False

        if event.type == EventType.ON_CONVERSATION_TURN_STARTED:
            self.bus.post(ConversationStartEvent())
        elif event.type == EventType.ON_CONVERSATION_TURN_FINISHED:
            if not event.args.get('with_follow_on_turn'):
                self.bus.post(ConversationEndEvent())
        elif event.type == EventType.ON_CONVERSATION_TURN_TIMEOUT:
            self.bus.post(ConversationTimeoutEvent())
        elif event.type == EventType.ON_NO_RESPONSE:
            self.bus.post(NoResponseEvent())
        elif hasattr(EventType, 'ON_RENDER_RESPONSE') and \
            event.type == EventType.ON_RENDER_RESPONSE:
            self.bus.post(ResponseEvent(response_text=event.args.get('text')))
        elif hasattr(EventType, 'ON_RESPONDING_STARTED') and \
                event.type == EventType.ON_RESPONDING_STARTED and \
                event.args.get('is_error_response', False) is True:
            self.logger.warning('Assistant response error')
        elif event.type == EventType.ON_RECOGNIZING_SPEECH_FINISHED:
            phrase = event.args['text'].lower().strip()
            self.logger.info('Speech recognized: {}'.format(phrase))
            self.bus.post(SpeechRecognizedEvent(phrase=phrase))
        elif event.type == EventType.ON_ALERT_STARTED:
            if event.args.get('alert_type') == AlertType.ALARM:
                self.bus.post(AlarmStartedEvent())
            elif event.args.get('alert_type') == AlertType.TIMER:
                self.bus.post(TimerStartedEvent())
            else:
                self.bus.post(AlertStartedEvent())
        elif event.type == EventType.ON_ALERT_FINISHED:
            if event.args.get('alert_type') == AlertType.ALARM:
                self.bus.post(AlarmEndEvent())
            elif event.args.get('alert_type') == AlertType.TIMER:
                self.bus.post(TimerEndEvent())
            else:
                self.bus.post(AlertEndEvent())
        elif event.type == EventType.ON_ASSISTANT_ERROR:
            self._has_error = True
            if event.args.get('is_fatal'):
                self.logger.error('Fatal assistant error')
            else:
                self.logger.warning('Assistant error')


    def start_conversation(self):
        """ Starts an assistant conversation """
        if self.assistant:
            self.assistant.start_conversation()


    def stop_conversation(self):
        """ Stops an assistant conversation """
        if self.assistant:
            self.assistant.stop_conversation()


    def run(self):
        super().run()

        while not self.should_stop():
            self._has_error = False

            with Assistant(self.credentials, self.device_model_id) as assistant:
                self.assistant = assistant
                for event in assistant.start():
                    self._process_event(event)
                    if self._has_error:
                        self.logger.info('Restarting the assistant after ' +
                                         'an unrecoverable error')
                        time.sleep(5)
                        continue


# vim:sw=4:ts=4:et: