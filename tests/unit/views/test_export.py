from ddt import ddt, data
import mock

from tests import IntegrationFixture


@mock.patch('occams.studies.views.export.check_csrf_token')
class TestAdd(IntegrationFixture):

    def call_view(self, context, request):
        from occams.studies.views.export import add as view
        return view(context, request)

    def test_get_exportables(self, check_csrf_token):
        """
        It should render only published schemata
        """
        from datetime import date
        from pyramid import testing
        from occams.studies import Session, models

        # No schemata
        request = testing.DummyRequest()
        response = self.call_view(models.ExportFactory(request), request)
        self.assertEquals(len(response['exportables']), 3)  # Only pre-cooked

        # Not-yet-published schemata
        schema = models.Schema(
            name=u'vitals', title=u'Vitals')
        Session.add(schema)
        Session.flush()
        request = testing.DummyRequest()
        response = self.call_view(models.ExportFactory(request), request)
        self.assertEquals(len(response['exportables']), 3)

        # Published schemata
        schema.publish_date = date.today()
        Session.flush()
        request = testing.DummyRequest()
        response = self.call_view(models.ExportFactory(request), request)
        self.assertEquals(len(response['exportables']), 4)

    def test_post_empty(self, check_csrf_token):
        """
        It should raise validation errors on empty imput
        """
        from pyramid import testing
        from webob.multidict import MultiDict
        from occams.studies import models
        request = testing.DummyRequest(post=MultiDict())
        response = self.call_view(models.ExportFactory(request), request)
        self.assertIsNotNone(response['errors'])

    def test_post_non_existent_schema(self, check_csrf_token):
        """
        It should raise validation errors for non-existent schemata
        """
        from pyramid import testing
        from webob.multidict import MultiDict
        from occams.studies import models
        request = testing.DummyRequest(
            post=MultiDict([('contents', 'does_not_exist')]))
        response = self.call_view(models.ExportFactory(request), request)
        self.assertIn('Invalid selection', response['errors'][0])

    @mock.patch('occams.studies.tasks.make_export')  # Don't invoke subtasks
    def test_valid(self, make_export, check_csrf_token):
        """
        It should add an export record and initiate an async task
        """
        from datetime import date
        from pyramid import testing
        from pyramid.httpexceptions import HTTPFound
        from webob.multidict import MultiDict
        from occams.studies import Session, models

        self.config.include('occams.studies.routes')
        self.config.add_route('export_status', '/dummy')
        self.config.registry.settings['app.export.dir'] = '/tmp'

        Session.add(models.User(key=u'joe'))
        Session.flush()
        Session.info['user'] = u'joe'

        schema = models.Schema(
            name=u'vitals', title=u'Vitals', publish_date=date.today())
        Session.add(schema)
        Session.flush()

        self.config.testing_securitypolicy(userid='joe')
        request = testing.DummyRequest(
            post=MultiDict([
                ('contents', str('vitals'))
            ]))

        response = self.call_view(models.ExportFactory(request), request)
        check_csrf_token.assert_called_with(request)
        self.assertIsInstance(response, HTTPFound)
        self.assertEqual(response.location,
                         request.route_path('export_status'))
        export = Session.query(models.Export).one()
        self.assertEqual(export.owner_user.key, 'joe')

    def test_exceed_limit(self, check_csrf_token):
        """
        It should not let the user exceed their allocated export limit
        """
        from datetime import date
        from pyramid import testing
        from webob.multidict import MultiDict
        from occams.studies import Session, models

        self.config.registry.settings['app.export.limit'] = 0

        Session.add(models.User(key=u'joe'))
        Session.flush()
        Session.info['user'] = u'joe'

        previous_export = models.Export(
            owner_user=Session.query(models.User).filter_by(key='joe').one(),
            contents=[{
                u'name': u'vitals',
                u'title': u'Vitals',
                u'versions': [str(date.today())]}])
        Session.add(previous_export)
        Session.flush()

        # The renderer should know about it
        self.config.testing_securitypolicy(userid='joe')
        request = testing.DummyRequest()
        response = self.call_view(models.ExportFactory(request), request)
        self.assertTrue(response['exceeded'])

        # If the user insists, they'll get a validation error as well
        self.config.testing_securitypolicy(userid='joe')
        request = testing.DummyRequest(
            post=MultiDict([
                ('contents', 'vitals')
                ]))
        self.assertTrue(response['exceeded'])


class TestStatusJSON(IntegrationFixture):

    def call_view(self, context, request):
        from occams.studies.views.export import status_json as view
        return view(context, request)

    def test_get_current_user(self):
        """
        It should return the authenticated user's exports
        """
        from pyramid import testing
        from occams.studies import Session, models

        self.config.registry.settings['app.export.dir'] = '/tmp'
        self.config.include('occams.studies.routes')

        Session.add(models.User(key='joe'))
        Session.add(models.User(key='jane'))
        Session.flush()
        Session.info['user'] = 'joe'

        Session.add_all([
            models.Export(
                owner_user=(
                    Session.query(models.User)
                    .filter_by(key='joe')
                    .one()),
                contents=[],
                status='pending'),
            models.Export(
                owner_user=(
                    Session.query(models.User)
                    .filter_by(key='jane')
                    .one()),
                contents=[],
                status='pending')])
        Session.flush()

        self.config.testing_securitypolicy(userid='joe')
        request = testing.DummyRequest()
        response = self.call_view(models.ExportFactory(request), request)
        exports = response['exports']
        self.assertEquals(len(exports), 1)

    def test_ignore_expired(self):
        """
        It should not render expired exports.
        """
        from datetime import datetime, timedelta
        from pyramid import testing
        from occams.studies import Session, models

        EXPIRE_DAYS = 10

        self.config.registry.settings['app.export.expire'] = EXPIRE_DAYS
        self.config.registry.settings['app.export.dir'] = '/tmp'
        self.config.include('occams.studies.routes')

        Session.add(models.User(key=u'joe'))
        Session.flush()
        Session.info['user'] = u'joe'

        now = datetime.now()

        export = models.Export(
            owner_user=(
                Session.query(models.User)
                .filter_by(key='joe')
                .one()),
            contents=[],
            status='pending',
            create_date=now,
            modify_date=now)
        Session.add(export)
        Session.flush()

        self.config.testing_securitypolicy(userid='joe')
        request = testing.DummyRequest()
        response = self.call_view(models.ExportFactory(request), request)
        exports = response['exports']
        self.assertEquals(len(exports), 1)

        export.create_date = export.modify_date = \
            now - timedelta(EXPIRE_DAYS + 1)
        Session.flush()
        request = testing.DummyRequest()
        response = self.call_view(models.ExportFactory(request), request)
        exports = response['exports']
        self.assertEquals(len(exports), 0)


class TestCodebookJSON(IntegrationFixture):

    def call_view(self, context, request):
        from occams.studies.views.export import codebook_json as view
        return view(context, request)

    def test_file_not_specified(self):
        """
        It should return 404 if the file not specified
        """
        from pyramid import testing
        from pyramid.httpexceptions import HTTPNotFound
        from webob.multidict import MultiDict
        from occams.studies import models

        request = testing.DummyRequest(
            params=MultiDict([('file', '')])
        )

        with self.assertRaises(HTTPNotFound):
            self.call_view(models.ExportFactory(request), request)

    def test_file_not_exists(self):
        """
        It should return 404 if the file does not exist
        """
        from pyramid import testing
        from pyramid.httpexceptions import HTTPNotFound
        from webob.multidict import MultiDict
        from occams.studies import models

        request = testing.DummyRequest(
            params=MultiDict([('file', 'i_dont_exist')])
        )

        with self.assertRaises(HTTPNotFound):
            self.call_view(models.ExportFactory(request), request)

    def test_file(self):
        """
        It should return the json rows for the codebook fragment
        """
        from datetime import date
        from pyramid import testing
        from webob.multidict import MultiDict
        from occams.studies import Session, models

        Session.add(models.Schema(
            name=u'aform',
            title=u'',
            publish_date=date.today(),
            attributes={
                u'myfield': models.Attribute(
                    name=u'myfield',
                    title=u'',
                    type=u'string',
                    order=0
                    )
            }
        ))
        Session.flush()

        request = testing.DummyRequest(
            params=MultiDict([('file', 'aform')])
        )

        response = self.call_view(models.ExportFactory(request), request)
        self.assertIsNotNone(response)


class TestCodebookDownload(IntegrationFixture):

    def call_view(self, context, request):
        from occams.studies.views.export import codebook_download as view
        return view(context, request)

    def test_download(self):
        """
        It should allow downloading of entire codebook file
        """
        import os
        from pyramid import testing
        from pyramid.response import FileResponse
        from occams.studies.exports.codebook import FILE_NAME
        from occams.studies import models
        self.config.registry.settings['app.export.dir'] = '/tmp'
        name = '/tmp/' + FILE_NAME
        with open(name, 'w+b'):
            self.config.testing_securitypolicy(userid='jane')
            request = testing.DummyRequest()
            response = self.call_view(models.ExportFactory(request), request)
            self.assertIsInstance(response, FileResponse)
        os.remove(name)


@mock.patch('occams.studies.tasks.celery.control.revoke')
@mock.patch('occams.studies.views.export.check_csrf_token')
class TestDelete(IntegrationFixture):

    def call_view(self, context, request):
        from occams.studies.views.export import delete_json as view
        return view(context, request)

    def test_delete(self, check_csrf_token, revoke):
        """
        It should allow the owner of the export to cancel/delete the export
        """
        from pyramid import testing
        from pyramid.httpexceptions import HTTPOk
        from occams.studies import models, Session

        Session.add(models.User(key=u'joe'))
        Session.flush()
        Session.info['user'] = u'joe'

        export = models.Export(
            owner_user=(
                Session.query(models.User)
                .filter_by(key='joe')
                .one()),
            contents=[],
            status='complete')
        Session.add(export)
        Session.flush()
        export_id = export.id
        export_name = export.name
        Session.expunge_all()

        self.config.testing_securitypolicy(userid='joe')
        request = testing.DummyRequest()
        response = self.call_view(export, request)
        check_csrf_token.assert_called_with(request)
        self.assertIsInstance(response, HTTPOk)
        self.assertIsNone(Session.query(models.Export).get(export_id))
        revoke.assert_called_with(export_name)


@ddt
class TestDownload(IntegrationFixture):

    def call_view(self, context, request):
        from occams.studies.views.export import download as view
        return view(context, request)

    @data('failed', 'pending')
    def test_get_not_found_status(self, status):
        """
        It should return 404 if the record is not ready
        """
        from pyramid import testing
        from pyramid.httpexceptions import HTTPNotFound
        from occams.studies import Session, models

        Session.add(models.User(key=u'joe'))
        Session.flush()
        Session.info['user'] = u'joe'

        export = models.Export(
            id=123,
            owner_user=(
                Session.query(models.User)
                .filter_by(key='joe')
                .one()),
            contents=[],
            status=status)
        Session.add(export)
        Session.flush()

        request = testing.DummyRequest()
        with self.assertRaises(HTTPNotFound):
            self.call_view(export, request)
