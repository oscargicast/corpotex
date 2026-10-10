"""Module-level aliases for the nested `TextChoices` of the models, because drf-spectacular's
`ENUM_NAME_OVERRIDES` resolves strings with `import_string` (module.attribute only). Imported
by spectacular at schema time, never by settings."""

from core.models import Customer, Material, OnboardingStyle, StyleVersion
from manager.models import Alert, Decision
from messaging.models import Conversation, Message, Turn
from operations.models import Order, OrderItem, Payment, PurchaseOrder, Route, RouteStop

ORDER_STATUS = Order.Status.choices
ORDER_STAGE = Order.Stage.choices
ORDER_RISK = Order.Risk.choices
ORDER_ITEM_CUSTOMIZATION = OrderItem.Customization.choices
PURCHASE_ORDER_STATUS = PurchaseOrder.Status.choices
PAYMENT_KIND = Payment.Kind.choices
PAYMENT_METHOD = Payment.Method.choices
ROUTE_STATUS = Route.Status.choices
ROUTE_STOP_KIND = RouteStop.Kind.choices
CUSTOMER_KIND = Customer.Kind.choices
MATERIAL_KIND = Material.Kind.choices
MATERIAL_UNIT = Material.Unit.choices
ONBOARDING_STYLE_STATUS = OnboardingStyle.Status.choices
ONBOARDING_STYLE_STEP = OnboardingStyle.Step.choices
STYLE_VERSION_SOURCE = StyleVersion.Source.choices
CONVERSATION_CHANNEL = Conversation.Channel.choices
MESSAGE_AUTHOR = Message.Author.choices
MESSAGE_STATUS = Message.Status.choices
TURN_REASON = Turn.Reason.choices
TURN_STATUS = Turn.Status.choices
DECISION_KIND = Decision.Kind.choices
DECISION_STATUS = Decision.Status.choices
ALERT_KIND = Alert.Kind.choices
ALERT_SEVERITY = Alert.Severity.choices
ALERT_STATUS = Alert.Status.choices
