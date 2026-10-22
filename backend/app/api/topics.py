from flask_restful import Resource

from ..schemas.content import topic_schema, topics_schema
from ..schemas.queries import TopicListQuerySchema
from ..services import topic_service
from ..utils.responses import success
from ._validation import load_query, require_slug

_query = TopicListQuerySchema()


class TopicListResource(Resource):
    def get(self):
        args = load_query(_query)
        topics = topic_service.list_topics(featured=args["featured"])
        return success(topics_schema.dump(topics), {"total": len(topics)})


class TopicDetailResource(Resource):
    def get(self, slug: str):
        topic = topic_service.get_topic(require_slug(slug, "Topic"))
        return success(topic_schema.dump(topic))
