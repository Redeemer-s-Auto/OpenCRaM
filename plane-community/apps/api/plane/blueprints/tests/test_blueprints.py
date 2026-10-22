# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Board blueprints: save, use, export, import, private boards and who may do what."""

import json

import pytest

from plane.blueprints import spec as S
from plane.blueprints.models import Blueprint, BlueprintVersion, BoardOrigin
from plane.db.models import (
    APIToken,
    CustomField,
    Issue,
    IssueTemplate,
    IssueView,
    Label,
    Project,
    ProjectMember,
    ProjectUserProperty,
    State,
    WorkspaceMember,
)

from .conftest import bp_url, client_for, make_user


def save(cast, client=None, expect=201, **data):
    data.setdefault("project_id", str(cast.alpha.id))
    data.setdefault("name", "Call-back board")
    response = (client or cast.author_client).post(bp_url(cast), data, format="json")
    assert response.status_code == expect, getattr(response, "data", None)
    return response.data


def use(cast, blueprint_id, client=None, expect=201, slug=None, **data):
    data.setdefault("name", "Second board")
    data.setdefault("identifier", "SEC")
    url = f"/api/workspaces/{slug or cast.workspace.slug}/blueprints/{blueprint_id}/use/"
    response = (client or cast.author_client).post(url, data, format="json")
    assert response.status_code == expect, getattr(response, "data", None)
    return response.data


def design(project):
    """Everything a blueprint copies, with ids swapped for names, so two boards can be compared."""
    states = {str(s.id): s.name for s in State.all_state_objects.filter(project=project)}
    labels = {str(l.id): l.name for l in Label.objects.filter(project=project)}
    fields = list(CustomField.objects.filter(project=project, archived_at__isnull=True).order_by("sort_order"))
    names = {str(f.id): f.name for f in fields}
    options = {str(o["id"]): o["name"] for f in fields for o in (f.options or [])}
    lookup = {**states, **labels, **names, **options}

    def named(value):
        if isinstance(value, str):
            return S.UUID_RE.sub(lambda m: f"<{lookup.get(m.group(0), '?')}>", value)
        if isinstance(value, list):
            return [named(v) for v in value]
        if isinstance(value, dict):
            return {named(k): named(v) for k, v in value.items()}
        return value

    def field_design(f):
        settings = dict(f.settings or {})
        if f.field_type == "relation":
            target = settings.get("target_project_id")
            settings = {
                "target": "self" if target == str(project.id) else Project.objects.get(pk=target).name,
                "two_way": settings.get("two_way"),
                "is_mirror": settings.get("is_mirror"),
            }
        return (f.name, f.field_type, [o["name"] for o in f.options or []], named(settings))

    return {
        "states": sorted((s.name, s.group, s.color, s.default) for s in State.objects.filter(project=project)),
        "labels": sorted(
            (l.name, l.color, l.parent.name if l.parent_id else None) for l in Label.objects.filter(project=project)
        ),
        "fields": [field_design(f) for f in fields],
        "views": [
            (v.name, named(v.filters), named(v.display_filters), named(v.display_properties), named(v.rich_filters))
            for v in IssueView.objects.filter(project=project)
        ],
        "templates": [(t.name, named(t.data)) for t in IssueTemplate.objects.filter(project=project)],
        "settings": {k: getattr(project, k) for k in S.BOARD_SETTINGS},
    }


def layout_of(project, user):
    prop = ProjectUserProperty.objects.get(project=project, user=user)
    names = {str(f.id): f.name for f in CustomField.objects.filter(project=project)}
    return {
        "display_filters": prop.display_filters,
        "display_properties": {S.UUID_RE.sub(lambda m: names[m.group(0)], k): v for k, v in prop.display_properties.items()},
    }


@pytest.mark.django_db
class TestRoundTrip:
    def test_board_to_blueprint_to_board_is_the_same_design(self, cast, board):
        saved = save(cast)
        assert saved["version"] == 1
        assert saved["summary"]["fields"] == 10  # mirror field remade from its relation, not stored twice
        pick = saved["summary"]["pick_boards"][0]["key"]
        result = use(cast, saved["id"], relation_targets={pick: str(cast.beta.id)})
        new = Project.objects.get(pk=result["project"]["id"])
        assert result["notes"] == []

        before, after = design(cast.alpha), design(new)
        # The view drops the assignee (a person); everything else matches.
        before["views"][0][1].pop("assignees")
        after["views"][0][1].pop("assignees", None)
        for key in ("states", "labels", "fields", "templates"):
            assert after[key] == before[key], key
        assert after["views"] == before["views"]
        assert after["settings"] == {**before["settings"], "is_private": False}

        # Formula, relations, mirror and rollups point inside the new board.
        fields = {f.name: f for f in CustomField.objects.filter(project=new)}
        assert fields["Total"].settings["expression"] == 'prop("Amount") + prop("Hours") * 165'
        assert fields["Related"].settings["target_project_id"] == str(new.id)
        assert fields["Related from"].settings["is_mirror"] is True
        assert fields["Related from"].project_id == new.id
        assert fields["Beta cards"].settings["target_project_id"] == str(cast.beta.id)
        assert fields["Related hours"].settings["relation_field_id"] == str(fields["Related"].id)
        assert fields["Related hours"].settings["target_field_id"] == str(fields["Hours"].id)

        # The saver's layout (gallery, shown fields) is the new board's starting layout.
        assert layout_of(new, cast.author) == layout_of(cast.alpha, cast.author)
        # Creator is admin; origin is remembered.
        assert ProjectMember.objects.get(project=new, member=cast.author).role == 20
        origin = BoardOrigin.objects.get(project=new)
        assert (origin.blueprint_id, origin.version) == (Blueprint.objects.get().id, 1)
        assert result["sample_cards_created"] == 0
        assert Issue.issue_objects.filter(project=new).count() == 0

    def test_external_relation_without_a_board_is_left_out_with_a_note(self, cast, board):
        saved = save(cast)
        assert [(p["name"], p["board_name"]) for p in saved["summary"]["pick_boards"]] == [("Beta cards", "Beta")]
        result = use(cast, saved["id"])
        new = Project.objects.get(pk=result["project"]["id"])
        assert not CustomField.objects.filter(project=new, name="Beta cards").exists()
        assert any("Beta cards" in note for note in result["notes"])

    def test_sample_cards_with_repeat_rules(self, cast, board):
        saved = save(cast, include_samples=True, include_repeat_rules=True)
        doc = Blueprint.objects.get(pk=saved["id"]).spec
        names = [c["name"] for c in doc["sample_cards"]]
        assert names == ["Sample card"]  # the restricted card never goes in
        assert "SECRETNAME" not in json.dumps(doc)
        body = doc["sample_cards"][0]["description_html"]
        assert "mention-component" not in body and "Phone the client" in body
        result = use(cast, saved["id"])
        assert result["sample_cards_created"] == 1
        card = Issue.issue_objects.get(project_id=result["project"]["id"])
        assert card.name == "Sample card"
        assert list(Label.objects.filter(labels=card).values_list("name", flat=True)) == ["Area"]
        from plane.recurrence.models import RepeatRule

        rule = RepeatRule.objects.get(issue=card)
        assert (rule.frequency, rule.weekdays, rule.timezone) == ("weekly", [0, 3], "America/Chicago")

    def test_repeat_rules_are_off_by_default(self, cast, board):
        saved = save(cast, include_samples=True)
        assert "repeat" not in Blueprint.objects.get(pk=saved["id"]).spec["sample_cards"][0]

    def test_update_from_board_makes_a_new_version(self, cast, board):
        saved = save(cast)
        State.objects.create(name="Parked", project=cast.alpha, workspace=cast.workspace, group="backlog", color="#000000")
        response = cast.author_client.post(bp_url(cast, f"{saved['id']}/recapture/"), {}, format="json")
        assert response.status_code == 200, response.data
        assert response.data["version"] == 2
        assert BlueprintVersion.objects.filter(blueprint_id=saved["id"]).count() == 2
        result = use(cast, saved["id"], identifier="THR", name="Third board")
        assert State.objects.filter(project_id=result["project"]["id"], name="Parked").exists()
        origin = cast.author_client.get(
            f"/api/workspaces/{cast.workspace.slug}/projects/{result['project']['id']}/blueprint-origin/"
        )
        assert origin.data == {"blueprint_id": saved["id"], "blueprint_name": "Call-back board", "version": 2}

    def test_rename_describe_and_delete(self, cast, board):
        saved = save(cast)
        url = bp_url(cast, f"{saved['id']}/")
        response = cast.author_client.patch(url, {"name": "Call backs", "description": "For follow-ups"}, format="json")
        assert response.status_code == 200 and response.data["name"] == "Call backs"
        result = use(cast, saved["id"])
        assert cast.author_client.delete(url).status_code == 204
        origin = cast.author_client.get(
            f"/api/workspaces/{cast.workspace.slug}/projects/{result['project']['id']}/blueprint-origin/"
        )
        assert origin.data == {"blueprint_id": None, "blueprint_name": "Call backs", "version": 1}


@pytest.mark.django_db
class TestExportImport:
    def test_export_holds_no_ids_or_emails(self, cast, board):
        saved = save(cast)
        response = cast.author_client.get(bp_url(cast, f"{saved['id']}/export/"))
        assert response.status_code == 200
        assert "attachment" in response["Content-Disposition"]
        text = response.content.decode()
        doc = json.loads(text)
        assert S.find_ids(doc) == [] and S.find_emails(doc) == []
        source_ids = [cast.alpha.id, cast.beta.id, cast.workspace.id, cast.author.id, cast.friend.id, cast.owner.id]
        source_ids += [s.id for s in State.all_state_objects.filter(project=cast.alpha)]
        source_ids += [f.id for f in CustomField.objects.filter(project=cast.alpha)]
        for source_id in source_ids:
            assert str(source_id) not in text
        for person in (cast.author, cast.friend, cast.owner):
            assert person.email not in text
        assert doc["format"] == S.FORMAT and doc["schema_version"] == 1 and doc["name"] == "Call-back board"

    def test_export_import_into_another_workspace_makes_the_same_board(self, cast, board, second_workspace):
        saved = save(cast)
        doc = cast.author_client.get(bp_url(cast, f"{saved['id']}/export/")).json()
        w = second_workspace
        url = f"/api/workspaces/{w.workspace.slug}/blueprints/import/"
        imported = w.client.post(url, {"document": doc}, format="json")
        assert imported.status_code == 201, imported.data
        assert imported.data["version"] == 1 and imported.data["name"] == "Call-back board"
        result = use(cast, imported.data["id"], client=w.client, slug=w.workspace.slug)
        new = Project.objects.get(pk=result["project"]["id"])
        assert new.workspace_id == w.workspace.id
        before, after = design(cast.alpha), design(new)
        before["views"][0][1].pop("assignees")
        after["views"][0][1].pop("assignees", None)
        # No board was picked for "Beta cards" in the new workspace, so it is left out.
        before["fields"] = [f for f in before["fields"] if f[0] != "Beta cards"]
        for key in ("states", "labels", "fields", "templates", "views"):
            assert after[key] == before[key], key
        assert any("Beta cards" in note for note in result["notes"])
        assert ProjectMember.objects.get(project=new, member=w.owner).role == 20

    def test_import_refuses_ids_emails_and_other_files(self, cast, board, second_workspace):
        saved = save(cast)
        doc = cast.author_client.get(bp_url(cast, f"{saved['id']}/export/")).json()
        url = f"/api/workspaces/{second_workspace.workspace.slug}/blueprints/import/"
        client = second_workspace.client

        with_id = json.loads(json.dumps(doc))
        with_id["views"][0]["filters"]["state"] = [str(board.waiting.id)]
        assert client.post(url, {"document": with_id}, format="json").status_code == 400

        with_email = json.loads(json.dumps(doc))
        with_email["description"] = "ask boss@example.com"
        assert client.post(url, {"document": with_email}, format="json").status_code == 400

        newer = {**doc, "schema_version": 99}
        response = client.post(url, {"document": newer}, format="json")
        assert response.status_code == 400 and "newer" in str(response.data)

        assert client.post(url, {"document": {"hello": 1}}, format="json").status_code == 400
        assert client.post(url, {"document": [1, 2]}, format="json").status_code == 400

    def test_import_name_clash_gets_a_number(self, cast, board):
        saved = save(cast)
        doc = cast.author_client.get(bp_url(cast, f"{saved['id']}/export/")).json()
        response = cast.owner_client.post(bp_url(cast, "import/"), {"document": doc}, format="json")
        assert response.status_code == 201 and response.data["name"] == "Call-back board (2)"

    def test_sample_cards_are_left_out_by_default(self, cast, board):
        with_samples = save(cast, name="With samples", include_samples=True, include_repeat_rules=True)
        # Inside the workspace the blueprint keeps its sample cards ...
        assert with_samples["summary"]["sample_cards"] == 1
        # ... but a plain export has none, says so, and carries no warning.
        doc = cast.author_client.get(bp_url(cast, f"{with_samples['id']}/export/")).json()
        assert doc["sample_cards"] == []
        assert "warning" not in doc
        assert any("Sample cards were left out" in note for note in doc["notes"])
        text = json.dumps(doc)
        assert '"Sample card"' not in text and "Phone the client" not in text and "weekly" not in text
        # Exporting twice does not pile up the note; the stored blueprint is unchanged.
        from plane.blueprints.service import SAMPLES_NOT_EXPORTED

        again = cast.author_client.get(bp_url(cast, f"{with_samples['id']}/export/?include_samples=0")).json()
        assert again["sample_cards"] == [] and again["notes"].count(SAMPLES_NOT_EXPORTED) == 1
        stored = Blueprint.objects.get(pk=with_samples["id"]).spec
        assert len(stored["sample_cards"]) == 1 and SAMPLES_NOT_EXPORTED not in stored["notes"]
        # A blueprint without sample cards gets no such note.
        plain = save(cast, name="Plain")
        plain_doc = cast.author_client.get(bp_url(cast, f"{plain['id']}/export/")).json()
        assert plain_doc["sample_cards"] == [] and SAMPLES_NOT_EXPORTED not in plain_doc["notes"]
        # Asking for sample cards on a blueprint that has none: no cards, no warning.
        plain_doc = cast.author_client.get(bp_url(cast, f"{plain['id']}/export/?include_samples=1")).json()
        assert plain_doc["sample_cards"] == [] and "warning" not in plain_doc

    def test_export_with_sample_cards_carries_them_and_the_warning(self, cast, board):
        from plane.blueprints.service import SAMPLE_EMAILS_REMOVED, SAMPLES_NOT_EXPORTED
        from plane.db.models import Issue as IssueModel, User

        saved = save(cast, name="With samples", include_samples=True, include_repeat_rules=True)
        response = cast.author_client.get(bp_url(cast, f"{saved['id']}/export/?include_samples=1"))
        assert response.status_code == 200
        text = response.content.decode()
        doc = json.loads(text)
        # The cards are there, with the warning inside the file.
        assert S.sample_card_titles(doc) == ["Sample card"]
        assert "Phone the client" in doc["sample_cards"][0]["description_html"]
        assert doc["sample_cards"][0]["repeat"]["frequency"] == "weekly"
        assert doc["warning"] == S.SAMPLE_CARDS_WARNING
        assert "Never include real client, team member, vehicle, money or shop records." in doc["warning"]
        assert SAMPLES_NOT_EXPORTED not in doc["notes"]
        # Still no ids, emails, people, mentions or images; hidden cards never go in.
        assert S.find_ids(doc) == [] and S.find_emails(doc) == []
        assert "person@example.org" not in text and SAMPLE_EMAILS_REMOVED in doc["notes"]
        assert "mention-component" not in text and "image-component" not in text and "<img" not in text
        assert "SECRETNAME" not in text and "Hidden card" not in text
        for person in User.objects.all():
            assert str(person.id) not in text
            assert not person.email or person.email not in text
        for card_id in IssueModel.all_objects.filter(workspace=cast.workspace).values_list("id", flat=True):
            assert str(card_id) not in text
        for source_id in (cast.workspace.id, cast.alpha.id, cast.beta.id):
            assert str(source_id) not in text
        beta_field = next(f for f in doc["fields"] if f["name"] == "Beta cards")
        assert beta_field["settings"]["board_name"] is None
        # The stored blueprint is unchanged, and the file is one this app accepts.
        stored = Blueprint.objects.get(pk=saved["id"]).spec
        assert "warning" not in stored and SAMPLE_EMAILS_REMOVED not in stored["notes"]
        S.validate_document(doc)

    def test_import_with_sample_cards_shows_the_warning_and_titles_first(self, cast, board, second_workspace):
        saved = save(cast, name="With samples", include_samples=True, include_repeat_rules=True)
        doc = cast.author_client.get(bp_url(cast, f"{saved['id']}/export/?include_samples=1")).json()
        w = second_workspace
        url = f"/api/workspaces/{w.workspace.slug}/blueprints/import/"
        # Without a yes: refused, with the warning and the card titles; nothing is made.
        for body in ({"document": doc}, {"document": doc, "accept_sample_cards": False}, doc):
            response = w.client.post(url, body, format="json")
            assert response.status_code == 400, response.data
            assert list(response.data["sample_cards"]) == ["Sample card"]
            assert str(response.data["warning"]) == S.SAMPLE_CARDS_WARNING
            assert S.SAMPLE_CARDS_WARNING in str(response.data["error"])
        assert not Blueprint.objects.filter(workspace=w.workspace).exists()
        # With a yes: imported with its sample cards; the warning is not stored.
        response = w.client.post(url, {"document": doc, "accept_sample_cards": True}, format="json")
        assert response.status_code == 201, response.data
        assert response.data["summary"]["sample_cards"] == 1
        stored = Blueprint.objects.get(pk=response.data["id"]).spec
        assert "warning" not in stored
        result = use(cast, response.data["id"], client=w.client, slug=w.workspace.slug)
        assert result["sample_cards_created"] == 1
        card = Issue.issue_objects.get(project_id=result["project"]["id"])
        assert card.name == "Sample card"

    def test_import_refuses_a_bad_warning_field(self, cast, board, second_workspace):
        saved = save(cast)
        doc = cast.author_client.get(bp_url(cast, f"{saved['id']}/export/")).json()
        url = f"/api/workspaces/{second_workspace.workspace.slug}/blueprints/import/"
        response = second_workspace.client.post(url, {"document": {**doc, "warning": ["x"]}}, format="json")
        assert response.status_code == 400

    def test_exported_file_holds_no_shop_data(self, cast, board):
        """The file a church gets: structure only. No card content, people, emails, ids or other boards' names."""
        from plane.db.models import Issue as IssueModel, User, Workspace

        # Give everything that is shop data a name that cannot appear by chance.
        Workspace.objects.filter(pk=cast.workspace.pk).update(name="Zqx Motors Workspace")
        for n, person in enumerate(User.objects.all()):
            User.objects.filter(pk=person.pk).update(
                first_name=f"Qfirst{n}", last_name=f"Qlast{n}", display_name=f"qdisplay{n}"
            )
        Project.objects.filter(pk=cast.beta.pk).update(name="Zqx Client Board")
        IssueModel.objects.filter(pk=board.card.pk).update(name="Zqx client Jane Roe 555-0100")
        # A person field value and an assignee on the template name a person by id.
        template = IssueTemplate.objects.get(pk=board.template.pk)
        template.data = {
            **template.data,
            "custom_fields": {**template.data["custom_fields"], str(board.owner["id"]): str(cast.friend.id)},
            "description_html": template.data["description_html"]
            + f'<mention-component entity_identifier="{cast.friend.id}"></mention-component>',
        }
        template.save()

        saved = save(cast, include_samples=True, include_repeat_rules=True, description="For call-backs")
        response = cast.author_client.get(bp_url(cast, f"{saved['id']}/export/"))
        assert response.status_code == 200
        text = response.content.decode()
        doc = json.loads(text)

        # Structure is there.
        assert {"Todo", "Waiting", "Done"} <= {s["name"] for s in doc["states"]}
        assert {"Area", "Front"} <= {label["name"] for label in doc["labels"]}
        assert {f["name"] for f in doc["fields"]} >= {"Reference", "Amount", "Kind", "Owner", "Total", "Related"}
        assert [t["name"] for t in doc["templates"]] == ["New call-back"]
        # Card contents are not.
        assert doc["sample_cards"] == []
        for card_text in ("Zqx client", "Jane Roe", "555-0100", "Phone the client", "SECRETNAME", "Hidden card"):
            assert card_text not in text, card_text
        # No ids of anything in the source workspace, anywhere.
        assert S.find_ids(doc) == []
        source_ids = {cast.workspace.id, cast.alpha.id, cast.beta.id}
        source_ids |= set(User.objects.values_list("id", flat=True))
        source_ids |= set(State.all_state_objects.filter(workspace=cast.workspace).values_list("id", flat=True))
        source_ids |= set(Label.objects.filter(workspace=cast.workspace).values_list("id", flat=True))
        source_ids |= set(IssueModel.all_objects.filter(workspace=cast.workspace).values_list("id", flat=True))
        source_ids |= set(IssueView.objects.filter(workspace=cast.workspace).values_list("id", flat=True))
        source_ids |= set(IssueTemplate.objects.filter(workspace=cast.workspace).values_list("id", flat=True))
        for field in CustomField.objects.filter(workspace=cast.workspace):
            source_ids.add(field.id)
            source_ids |= {o["id"] for o in field.options or [] if isinstance(o, dict) and o.get("id")}
        for source_id in source_ids:
            assert str(source_id) not in text, source_id
        # No people: no emails, names, or who-made-it fields.
        assert S.find_emails(doc) == []
        for person in User.objects.all():
            for value in (person.email, person.username, person.first_name, person.last_name, person.display_name):
                assert not value or value not in text, value
        # Who-made-it keys may only appear empty (a saved view's filter list, emptied of people).
        people_keys = {"created_by", "updated_by", "owned_by", "assignees", "subscriber", "mentions", "lead"}
        place_keys = {"workspace", "workspace_id", "project_id", "source_project"}

        def values_at(value, keys):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in keys:
                        yield key, item
                    yield from values_at(item, keys)
            elif isinstance(value, list):
                for item in value:
                    yield from values_at(item, keys)

        assert [kv for kv in values_at(doc, people_keys) if kv[1]] == []
        assert list(values_at(doc, place_keys)) == []
        # No workspace or other board names (the receiver picks their own board for a relation).
        assert "Zqx" not in text and cast.workspace.slug not in text
        beta_field = next(f for f in doc["fields"] if f["name"] == "Beta cards")
        assert beta_field["settings"]["board_name"] is None
        # Inside the workspace, the picker still shows which board it linked to.
        assert saved["summary"]["pick_boards"][0]["board_name"] == "Zqx Client Board"
        # And the file is still one this app accepts.
        S.validate_document(doc)


@pytest.mark.django_db
class TestPrivateBoards:
    def test_private_board_blueprint_starts_unshared_and_makes_private_boards(self, cast, board):
        Project.objects.filter(pk=cast.alpha.pk).update(is_private=True)
        saved = save(cast)
        assert saved["is_shared"] is False and saved["summary"]["is_private"] is True
        # Another member of the workspace does not see it.
        assert cast.outsider_client.get(bp_url(cast)).data == []
        assert cast.outsider_client.get(bp_url(cast, f"{saved['id']}/")).status_code == 404
        use(cast, saved["id"], client=cast.outsider_client, expect=404)
        # Its saver makes a private board they are the only member of.
        result = use(cast, saved["id"])
        new = Project.objects.get(pk=result["project"]["id"])
        assert new.is_private is True
        assert list(ProjectMember.objects.filter(project=new).values_list("member_id", flat=True)) == [cast.author.id]

    def test_workspace_admin_not_on_private_board_cannot_save_it(self, cast, board):
        Project.objects.filter(pk=cast.alpha.pk).update(is_private=True)
        admin = make_user("admin2")
        WorkspaceMember.objects.create(workspace=cast.workspace, member=admin, role=20)
        save(cast, client=client_for(admin), expect=404)

    def test_board_name_of_a_private_target_is_not_written(self, cast, board):
        Project.objects.filter(pk=cast.beta.pk).update(is_private=True)
        ProjectMember.objects.filter(project=cast.beta, member=cast.author).delete()
        saved = save(cast)
        doc = Blueprint.objects.get(pk=saved["id"]).spec
        beta_field = next(f for f in doc["fields"] if f["name"] == "Beta cards")
        assert beta_field["settings"]["board_name"] is None


@pytest.mark.django_db
class TestPermissions:
    def test_plain_board_member_cannot_save(self, cast, board):
        save(cast, client=cast.insider_client, expect=403)

    def test_board_hidden_from_member_answers_404(self, cast, board):
        Project.objects.filter(pk=cast.alpha.pk).update(is_private=True)
        save(cast, client=cast.outsider_client, expect=404)

    def test_bad_board_id_answers_404_not_500(self, cast, board):
        save(cast, project_id="not-a-board", expect=404)
        save(cast, project_id=None, expect=404)

    def test_workspace_admin_can_save_any_board_they_can_see(self, cast, board):
        save(cast, client=cast.owner_client)

    def test_member_can_use_but_not_change_a_shared_blueprint(self, cast, board):
        saved = save(cast)
        url = bp_url(cast, f"{saved['id']}/")
        assert cast.outsider_client.patch(url, {"name": "Mine"}, format="json").status_code == 403
        assert cast.outsider_client.delete(url).status_code == 403
        assert cast.outsider_client.get(bp_url(cast, f"{saved['id']}/export/")).status_code == 403
        use(cast, saved["id"], client=cast.outsider_client, identifier="OUT", name="Outsider board")
        # A workspace admin can manage a shared blueprint; only its saver can unshare it.
        assert cast.owner_client.patch(url, {"description": "x"}, format="json").status_code == 200
        assert cast.owner_client.patch(url, {"is_shared": False}, format="json").status_code == 400

    def test_guest_sees_nothing(self, cast, board):
        saved = save(cast)
        guest = make_user("guest")
        WorkspaceMember.objects.create(workspace=cast.workspace, member=guest, role=5)
        client = client_for(guest)
        assert client.get(bp_url(cast)).status_code == 403
        use(cast, saved["id"], client=client, expect=403)

    def test_other_workspace_cannot_reach_it(self, cast, board, second_workspace):
        saved = save(cast)
        url = f"/api/workspaces/{second_workspace.workspace.slug}/blueprints/{saved['id']}/"
        assert second_workspace.client.get(url).status_code == 404


@pytest.mark.django_db
class TestPublicApi:
    def _client(self, user, workspace):
        from rest_framework.test import APIClient

        token = APIToken.objects.create(user=user, workspace=workspace, label="test")
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=token.token)
        return client

    def test_list_and_create_board(self, cast, board):
        saved = save(cast)
        client = self._client(cast.author, cast.workspace)
        base = f"/api/v1/workspaces/{cast.workspace.slug}/blueprints/"
        listing = client.get(base)
        assert listing.status_code == 200, listing.data
        assert [b["id"] for b in listing.data] == [saved["id"]]
        made = client.post(f"{base}{saved['id']}/create-board/", {"name": "From API", "identifier": "API"}, format="json")
        assert made.status_code == 201, made.data
        assert Project.objects.get(pk=made.data["project"]["id"]).name == "From API"
        assert client.delete(f"{base}{saved['id']}/").status_code == 405
