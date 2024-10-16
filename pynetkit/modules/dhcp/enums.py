#  Copyright (c) Kuba Szczodrzyński 2023-9-10.

from enum import IntEnum, IntFlag


class DhcpPacketType(IntEnum):
    BOOT_REQUEST = 1
    BOOT_REPLY = 2


class DhcpMessageType(IntEnum):
    DISCOVER = 1
    OFFER = 2
    REQUEST = 3
    DECLINE = 4
    ACK = 5
    NAK = 6
    RELEASE = 7
    INFORM = 8
    FORCERENEW = 9
    LEASEQUERY = 10
    LEASEUNASSIGNED = 11
    LEASEUNKNOWN = 12
    LEASEACTIVE = 13
    BULKLEASEQUERY = 14
    LEASEQUERYDONE = 15
    ACTIVELEASEQUERY = 16
    LEASEQUERYSTATUS = 17
    TLS = 18


class DhcpBootpFlags(IntFlag):
    BROADCAST = 1 << 15


class DhcpOptionType(IntEnum):
    SUBNET_MASK = 1
    TIME_OFFSET = 2
    ROUTER = 3
    TIME_SERVERS = 4
    NAME_SERVERS = 5
    DNS_SERVERS = 6
    LOG_SERVERS = 7
    COOKIE_SERVERS = 8
    LPR_SERVERS = 9
    IMPRESS_SERVERS = 10
    RLP_SERVERS = 11
    HOST_NAME = 12
    BOOT_FILE_SIZE = 13
    MERIT_DUMP_FILE = 14
    DOMAIN_NAME = 15
    SWAP_SERVER = 16
    ROOT_PATH = 17
    EXTENSION_FILE = 18
    IP_LAYER_FORWARDING_ = 19
    SRC_ROUTE_ENABLER = 20
    POLICY_FILTER = 21
    MAXIMUM_DG_REASSEMBLY_SIZE = 22
    DEFAULT_IP_TTL = 23
    PATH_MTU_AGING_TIMEOUT = 24
    MTU_PLATEAU_ = 25
    INTERFACE_MTU_SIZE = 26
    ALL_SUBNETS_ARE_LOCAL = 27
    BROADCAST_ADDRESS = 28
    PERFORM_MASK_DISCOVERY = 29
    PROVIDE_MASK_TO_OTHERS = 30
    PERFORM_ROUTER_DISCOVERY = 31
    ROUTER_SOLICITATION_ADDRESS = 32
    STATIC_ROUTING_TABLE = 33
    TRAILER_ENCAPSULATION = 34
    ARP_CACHE_TIMEOUT = 35
    ETHERNET_ENCAPSULATION = 36
    DEFAULT_TCP_TIME_TO_LIVE = 37
    TCP_KEEPALIVE_INTERVAL = 38
    TCP_KEEPALIVE_GARBAGE = 39
    NIS_DOMAIN_NAME = 40
    NIS_SERVER_ADDRESSES = 41
    NTP_SERVERS_ADDRESSES = 42
    VENDOR_SPECIFIC_INFORMATION = 43
    NETBIOS_NAME_SERVER = 44
    NETBIOS_DATAGRAM_DISTRIBUTION_ = 45
    NETBIOS_NODE_TYPE = 46
    NETBIOS_SCOPE = 47
    X_WINDOW_FONT_SERVER = 48
    X_WINDOW_DISPLAY_MANAGER = 49
    REQUESTED_IP_ADDRESS = 50
    IP_ADDRESS_LEASE_TIME = 51
    OPTION_OVERLOAD = 52
    MESSAGE_TYPE = 53
    SERVER_IDENTIFIER = 54
    PARAMETER_REQUEST_LIST = 55
    MESSAGE = 56
    MAXIMUM_MESSAGE_SIZE = 57
    RENEW_TIME_VALUE = 58
    REBINDING_TIME_VALUE = 59
    VENDOR_CLASS_IDENTIFIER = 60
    CLIENT_IDENTIFIER = 61
    NETWARE_IP_DOMAIN_NAME = 62
    NETWARE_IP_SUB_OPTIONS = 63
    NIS_V3_CLIENT_DOMAIN_NAME = 64
    NIS_V3_SERVER_ADDRESS = 65
    TFTP_SERVER_NAME = 66
    BOOT_FILE_NAME = 67
    HOME_AGENT_ADDRESSES = 68
    SIMPLE_MAIL_SERVER_ADDRESSES = 69
    POST_OFFICE_SERVER_ADDRESSES = 70
    NETWORK_NEWS_SERVER_ADDRESSES = 71
    WWW_SERVER_ADDRESSES = 72
    FINGER_SERVER_ADDRESSES = 73
    CHAT_SERVER_ADDRESSES = 74
    STREETTALK_SERVER_ADDRESSES = 75
    STREETTALK_DIRECTORY_ASSISTANCE_ADDRESSES = 76
    USER_CLASS_INFORMATION = 77
    SLP_DIRECTORY_AGENT = 78
    SLP_SERVICE_SCOPE = 79
    RAPID_COMMIT = 80
    FQDN = 81
    RELAY_AGENT_INFORMATION = 82
    INTERNET_STORAGE_NAME_SERVICE = 83
    NOVELL_DIRECTORY_SERVERS = 85
    NOVELL_DIRECTORY_SERVER_TREE_NAME = 86
    NOVELL_DIRECTORY_SERVER_CONTEXT = 87
    BCMCS_CONTROLLER_DOMAIN_NAME_LIST = 88
    BCMCS_CONTROLLER_IPV4_ADDRESS_LIST = 89
    AUTHENTICATION = 90
    CLIENT_SYSTEM = 93
    CLIENT_NETWORK_DEVICE_INTERFACE = 94
    LDAP_USE = 95
    UUID_BASED_CLIENT_IDENTIFIER = 97
    OPEN_GROUP_USER_AUTHENTICATION = 98
    IPV6_ONLY_PREFERRED = 108
    DHCP_CAPTIVE_PORTAL = 114
    DOMAIN_SEARCH = 119
    CLASSLESS_STATIC_ROUTE = 121
    PRIVATE = 224
    PRIVATE_CLASSLESS_STATIC_ROUTE = 249
    PRIVATE_PROXY_AUTODISCOVERY = 252
    END = 255
