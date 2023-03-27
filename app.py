import time
from github import Github, InputGitTreeElement
import os
import requests
import subprocess
from threading import Thread
from flask import Flask, request
import json
import yaml

# TODO: watch out ips and ports

BL_ENGINE_IP = os.getenv("BL_ENGINE_IP", "0.0.0.0")
MINIKUBE_IP = os.getenv("MINIKUBE_IP", "")
H_SDNC_IP = os.getenv("H_SDNC_IP", "")
BL_ENGINE_PORT = int(os.getenv("BL_ENGINE_PORT", 5002))
app = Flask(__name__)
MASTER_BRANCH = "main"  # Same for both
GITHUB_ARGOCD_TOKEN = ""
REPO_TOPOLOGY = "javoerrea/optical-topology"
REPO_DEPLOYMENT = "javoerrea/optical-control-plane"

RESTCONF_BASE_URL = ""
RESTS_BASE_URL = ""
URL_CONFIG_NETCONF_TOPO = "{}/config/network-topology:network-topology/topology/topology-netconf/"

ODL_LOGIN = "admin"
ODL_PWD = "admin"
NODES_LOGIN = "admin"
NODES_PWD = "admin"

TYPE_APPLICATION_JSON = {'Content-Type': 'application/json', 'Accept': 'application/json'}
TYPE_APPLICATION_XML = {'Content-Type': 'application/xml', 'Accept': 'application/xml'}

CODE_SHOULD_BE_200 = 'Http status code should be 200'
CODE_SHOULD_BE_201 = 'Http status code should be 201'

g = Github(GITHUB_ARGOCD_TOKEN)
topology_repo = g.get_repo(REPO_TOPOLOGY)
deployment_repo = g.get_repo(REPO_DEPLOYMENT)


def push_fully_to_repo(controller_deployment_yaml, oia_pce_deployment_yaml, oia_pce_service_yaml):
    # Create blobs for each file
    blob1, blob2, blob3 = [
        deployment_repo.create_git_blob(
            content=controller_deployment_yaml,
            encoding='utf-8',
        ),
        deployment_repo.create_git_blob(
            content=oia_pce_deployment_yaml,
            encoding='utf-8',
        ),
        deployment_repo.create_git_blob(
            content=oia_pce_service_yaml,
            encoding='utf-8',
        ),
    ]

    # Create a new tree with our blobs
    new_tree = deployment_repo.create_git_tree(
        tree=[
            InputGitTreeElement(
                path="ofc-demo/controller-depl.yaml",
                mode="100644",
                type="blob",
                sha=blob1.sha,
            ),
            InputGitTreeElement(
                path="ofc-demo/oia-pce-depl.yaml",
                mode="100644",
                type="blob",
                sha=blob2.sha,
            ),
            InputGitTreeElement(
                path="ofc-demo/ols-depl.yaml",
                mode="100644",
                type="blob",
                sha=None,
            ),
            InputGitTreeElement(
                path="ofc-demo/ols-svc.yaml",
                mode="100644",
                type="blob",
                sha=None,
            ),
            InputGitTreeElement(
                path="ofc-demo/oia-pce-svc.yaml",
                mode="100644",
                type="blob",
                sha=blob3.sha,
            ),
        ],
        base_tree=deployment_repo.get_git_tree(sha='main')
    )

    # Create a new commit with that tree on top of the current main branch head
    commit = deployment_repo.create_git_commit(
        message="Fully Disaggregated deployment",
        tree=deployment_repo.get_git_tree(sha=new_tree.sha),
        parents=[deployment_repo.get_git_commit(deployment_repo.get_branch('main').commit.sha)],
    )

    # Push that commit to the main branch by editing the reference
    main_ref = deployment_repo.get_git_ref(ref='heads/main')
    main_ref.edit(sha=commit.sha)


def push_partial_to_repo(controller_deployment_yaml, ols_deployment_yaml, ols_service_yaml):
    # Create blobs for each file
    blob1, blob2, blob3 = [
        deployment_repo.create_git_blob(
            content=controller_deployment_yaml,
            encoding='utf-8',
        ),
        deployment_repo.create_git_blob(
            content=ols_deployment_yaml,
            encoding='utf-8',
        ),
        deployment_repo.create_git_blob(
            content=ols_service_yaml,
            encoding='utf-8',
        )
    ]

    # Create a new tree with our blobs
    new_tree = deployment_repo.create_git_tree(
        tree=[
            InputGitTreeElement(
                path="ofc-demo/controller-depl.yaml",
                mode="100644",
                type="blob",
                sha=blob1.sha,
            ),
            InputGitTreeElement(
                path="ofc-demo/oia-pce-depl.yaml",
                mode="100644",
                type="blob",
                sha=None,
            ),
            InputGitTreeElement(
                path="ofc-demo/oia-pce-svc.yaml",
                mode="100644",
                type="blob",
                sha=None,
            ),
            InputGitTreeElement(
                path="ofc-demo/ols-depl.yaml",
                mode="100644",
                type="blob",
                sha=blob2.sha,
            ),
            InputGitTreeElement(
                path="ofc-demo/ols-svc.yaml",
                mode="100644",
                type="blob",
                sha=blob3.sha,
            )
        ],
        base_tree=deployment_repo.get_git_tree(sha='main')
    )

    # Create a new commit with that tree on top of the current main branch head
    commit = deployment_repo.create_git_commit(
        message="Partially Disaggregated deployment",
        tree=deployment_repo.get_git_tree(sha=new_tree.sha),
        parents=[deployment_repo.get_git_commit(deployment_repo.get_branch('main').commit.sha)],
    )

    # Push that commit to the main branch by editing the reference
    main_ref = deployment_repo.get_git_ref(ref='heads/main')
    main_ref.edit(sha=commit.sha)


@app.route('/topologyChange', methods=['POST'])
def transform():
    """Endpoint for a GitHub webhook, calling Travis API to trigger a build.
      """
    print("------------------INIT------------------")
    print("Topology change detected. Verifying number of nodes, links and vendors")
    print(request.json)
    topology_file = topology_repo.get_contents("inventory.json", ref=MASTER_BRANCH)
    network_inventory = topology_file.decoded_content.decode("utf-8")
    print(network_inventory)
    print("------------------TOPO. JSON FILE------------------")
    network_inventory_json = json.loads(network_inventory)
    node_list = network_inventory_json['topology']['nodes']
    link_list = network_inventory_json['topology']['links']
    vendor_list = []
    for node in node_list:
        if node['vendor'] not in vendor_list and node['type'] == 'ROADM':
            vendor_list.append(node['vendor'])
    print("------------------EXTRACTED DATA------------------")
    print("------------------NODES------------------")
    print(node_list)
    print("------------------LINKS------------------")
    print(link_list)
    print("------------------VENDORS------------------")
    print(vendor_list)
    print("------------------CHECKING DEPLOYMENT CHANGE------------------")
    controller_service_file = deployment_repo.get_contents("ofc-demo/controller-svc.yaml", ref=MASTER_BRANCH)
    controller_service = controller_service_file.decoded_content.decode("utf-8")
    controller_service_yaml = yaml.safe_load_all(controller_service)
    # port = "30181"
    # for svc_port in controller_service_yaml['spec']['ports']:
        # if svc_port['name'] == "gui-sdn":
            # port = svc_port['nodePort']
    # global MINIKUBE_IP
    # if MINIKUBE_IP == "":
        # MINIKUBE_IP = subprocess.run(['minikube', 'ip'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()
    # print(MINIKUBE_IP + ":" + port)
    if len(vendor_list) > 1:
        print("Multi vendor network. We need fully disaggregated scenario")
        controller_deployment_file = deployment_repo.get_contents("ofc-demo/controller-depl.yaml", ref=MASTER_BRANCH)
        controller_deployment = controller_deployment_file.decoded_content.decode("utf-8")
        controller_deployment_yaml = yaml.safe_load_all(controller_deployment)
        print("------------------OLD CONTROLLER DEPLOYMENT------------------")
        print(controller_deployment_yaml)
        new_controller_deployment_yaml = []
        for doc in controller_deployment_yaml:
            if doc['kind'] == "Deployment":
                containers = []
                for container in doc['spec']['template']['spec']['containers']:
                    if container['name'] == "h-sdnc":
                        container['image'] = "tqhuy812/nssr-controller-ofc2023:1.0.0"
                        container['name'] = "t-sdnc"
                    containers.append(container)
                doc['spec']['template']['spec']['containers'] = containers
            new_controller_deployment_yaml.append(doc)
        controller_deployment_yaml = yaml.dump_all(new_controller_deployment_yaml, default_flow_style=False)
        print("------------------NEW CONTROLLER DEPLOYMENT------------------")
        print(controller_deployment_yaml)
        print("------------------NEW OIA PCE DEPLOYMENT------------------")
        with open("k8s-templates/oia-pce-depl.yaml", "r") as stream:
            oia_pce_deployment_yaml = list(yaml.safe_load_all(stream))
        oia_pce_deployment_yaml = yaml.dump_all(oia_pce_deployment_yaml, default_flow_style=False)
        with open("k8s-templates/oia-pce-svc.yaml", "r") as stream:
            oia_pce_service_yaml = list(yaml.safe_load_all(stream))
        oia_pce_service_yaml = yaml.dump_all(oia_pce_service_yaml, default_flow_style=False)
        print(oia_pce_service_yaml)
        print("------------------PUSH. NEW TREE------------------")
        push_fully_to_repo(controller_deployment_yaml, oia_pce_deployment_yaml, oia_pce_service_yaml)
        # thread = Thread(target=recommissioning_fully, args=[node_list, link_list, MINIKUBE_IP, port])
        # thread.start()
    else:
        print("------------------GETTING TAPI SERVICES------------------")
        #response = tapi_get_services(MINIKUBE_IP, port)
        #response = response.json()
        #service_list = response['output']['service']
        #print(service_list)
        #if len(service_list) > 0:
            #print("------------------CLEANING OC DEVICES------------------")
            #for service in service_list:
                #try:
                    #delete_tapi_service(H_SDNC_IP, port, service['uuid'])
                #except requests.exceptions.RequestException and requests.exceptions.HTTPError:
                    #print("Could not delete oc cross connections")
                #print("------------------OC DEVICES CLEANED------------------")
        print("Single vendor network. We need partially disaggregated scenario")
        controller_deployment_file = deployment_repo.get_contents("ofc-demo/controller-depl.yaml", ref=MASTER_BRANCH)
        controller_deployment = controller_deployment_file.decoded_content.decode("utf-8")
        controller_deployment_yaml = yaml.safe_load_all(controller_deployment)
        print("------------------OLD CONTROLLER DEPLOYMENT------------------")
        print(controller_deployment_yaml)
        new_controller_deployment_yaml = []
        for doc in controller_deployment_yaml:
            if doc['kind'] == "Deployment":
                containers = []
                for container in doc['spec']['template']['spec']['containers']:
                    if container['name'] == "t-sdnc":
                        container['image'] = "tqhuy812/hsdnc-ofc2023:1.0.0"
                        container['name'] = "h-sdnc"
                    containers.append(container)
                doc['spec']['template']['spec']['containers'] = containers
            new_controller_deployment_yaml.append(doc)
        controller_deployment_yaml = yaml.dump_all(new_controller_deployment_yaml, default_flow_style=False)
        print("------------------NEW CONTROLLER DEPLOYMENT------------------")
        print(controller_deployment_yaml)
        print("------------------NEW OLS DEPLOYMENT------------------")
        with open("k8s-templates/ols-depl.yaml", "r") as stream:
            ols_deployment_yaml = list(yaml.safe_load_all(stream))
        ols_deployment_yaml = yaml.dump_all(ols_deployment_yaml, default_flow_style=False)
        print(ols_deployment_yaml)
        with open("k8s-templates/ols-svc.yaml", "r") as stream:
            ols_service_yaml = list(yaml.safe_load_all(stream))
        ols_service_yaml = yaml.dump_all(ols_service_yaml, default_flow_style=False)
        print(ols_service_yaml)
        print("------------------PUSH. NEW TREE------------------")
        push_partial_to_repo(controller_deployment_yaml, ols_deployment_yaml, ols_service_yaml)
        # thread = Thread(target=recommissioning_partially, args=[node_list, link_list, MINIKUBE_IP, port])
        # thread.start()
    return "DONE", 200


# @app.route('/', methods=['POST'])
def recommissioning_fully(node_list=None, link_list=None, ip="localhost", port="8181"):
    global RESTCONF_BASE_URL
    global RESTS_BASE_URL
    '''''
    with open("json-templates/inventory_full.json", "r") as stream:
        network_inventory = json.load(stream)
    print(network_inventory)
    print("------------------TOPO. JSON FILE------------------")
    network_inventory_json = network_inventory
    node_list = network_inventory_json['topology']['nodes']
    link_list = network_inventory_json['topology']['links']
    '''''
    RESTCONF_BASE_URL = "http://" + ip + ":" + port + "/restconf"
    RESTS_BASE_URL = "http://" + ip + ":" + port + "/rests"
    print("------------------INIT------------------")
    print("Recommissioning to controller")
    print("------------------WAITING FOR CONTROLLER------------------")
    while True:
        try:
            response = tapi_get_context_request()
            if response.status_code == 200:
                print("Controller is up")
                break
        except requests.exceptions.ConnectionError:
            print("Controller not up")
        time.sleep(10)
    time.sleep(20)  # giving time to load all bundles
    print("------------------COMMISSIONING DEVICES------------------")
    for node in node_list:
        if node['type'] == "TRANSPONDER":
            continue
        print("------------------NODE " + node['id'] + "------------------")
        mount_tapi_device(node['id'], node['host'], node['port'])
        time.sleep(10)
    print("------------------DONE WITH DEVICES------------------")
    print("------------------COMMISSIONING LINKS------------------")
    for link in link_list:
        if link['node-a']['type'] == "ROADM" and link['node-z']['type'] == "ROADM":
            connect_rdm_to_rdm_tapi_request(link['node-a']['id'], link['node-a']['port-id'], link['node-a']['port-dir'],
                                            link['node-z']['id'], link['node-z']['port-id'], link['node-z']['port-dir'])
            time.sleep(2)
        else:
            if link['node-a']['id'] == "1830-PSI-M-A1":
                connect_xpdr_to_rdm_tapi_request("1830-PSS-A1", "1-17-1", link['node-z']['id'],
                                                 link['node-z']['port-id'])
                time.sleep(2)
            if link['node-a']['id'] == "1830-PSI-M-B1":
                connect_xpdr_to_rdm_tapi_request("1830-PSS-B1", "1-14-1", link['node-z']['id'],
                                                 link['node-z']['port-id'])
                time.sleep(2)
    print("------------------DONE WITH LINKS------------------")
    time.sleep(5)
    print("------------------MAPPING PARTIALLY TO FULLY DISAGGREGATED CONTEXT------------------")
    with open("json-templates/tapi_t1_topo.json", "r") as stream:
        tapi_context = json.load(stream)  # TODO: we should send the string format version
    print(tapi_context)
    tapi_put_context_request(tapi_context)
    print("------------------MAPPING DONE------------------")
    print("------------------JOB COMPLETED------------------")


# @app.route('/', methods=['POST'])
def recommissioning_partially(node_list=None, link_list=None, ip="localhost", port="8181"):
    global RESTCONF_BASE_URL
    global RESTS_BASE_URL
    '''''
    with open("json-templates/inventory_partial.json", "r") as stream:
        network_inventory = json.load(stream)
    print(network_inventory)
    print("------------------TOPO. JSON FILE------------------")
    network_inventory_json = network_inventory
    node_list = network_inventory_json['topology']['nodes']
    '''''
    RESTCONF_BASE_URL = "http://" + ip + ":" + port + "/restconf"
    RESTS_BASE_URL = "http://" + ip + ":" + port + "/rests"
    print("------------------INIT------------------")
    print("Recommissioning to controller")
    print("------------------WAITING FOR CONTROLLER------------------")
    while True:
        try:
            response = tapi_get_context_request()
            if response.status_code == 200:
                print("Controller is up")
                break
        except requests.exceptions.ConnectionError:
            print("Controller not up")
        time.sleep(10)
    time.sleep(20)  # giving time to load all bundles
    print("------------------COMMISSIONING DEVICES------------------")
    for node in node_list:
        if node['type'] == "TRANSPONDER":
            continue
        print("------------------NODE " + node['id'] + "------------------")
        mount_tapi_device(node['id'], node['host'], node['port'])
        time.sleep(10)
    print("------------------DONE WITH DEVICES------------------")
    print("------------------JOB COMPLETED------------------")


def get_request(url):
    return requests.request(
        "GET", url.format(RESTS_BASE_URL),
        headers=TYPE_APPLICATION_JSON,
        auth=(ODL_LOGIN, ODL_PWD))


def post_request(url, data):
    if data:
        print(json.dumps(data))
        return requests.request(
            "POST", url.format(RESTCONF_BASE_URL),
            data=json.dumps(data),
            headers=TYPE_APPLICATION_JSON,
            auth=(ODL_LOGIN, ODL_PWD))

    return requests.request(
        "POST", url.format(RESTCONF_BASE_URL),
        headers=TYPE_APPLICATION_JSON,
        auth=(ODL_LOGIN, ODL_PWD))


def put_request(url, data):
    return requests.request(
        "PUT", url.format(RESTCONF_BASE_URL),
        data=json.dumps(data),
        headers=TYPE_APPLICATION_JSON,
        auth=(ODL_LOGIN, ODL_PWD))


def put_rests_request(url, data):
    return requests.request(
        "PUT", url.format(RESTS_BASE_URL),
        data=json.dumps(data),
        headers=TYPE_APPLICATION_JSON,
        auth=(ODL_LOGIN, ODL_PWD))


def delete_request(url):
    return requests.request(
        "DELETE", url.format(RESTCONF_BASE_URL),
        headers=TYPE_APPLICATION_JSON,
        auth=(ODL_LOGIN, ODL_PWD))


def tapi_put_context_request(context):
    url = "{}/operations/transportpce-tapinetworkutils:put-tapi-context"
    data = {
        "input": {
            "tapi-context-file": context
        }
    }
    return post_request(url, data)


def tapi_get_context_request(ip, port):
    global RESTCONF_BASE_URL
    global RESTS_BASE_URL
    RESTCONF_BASE_URL = "http://" + ip + ":" + port + "/restconf"
    RESTS_BASE_URL = "http://" + ip + ":" + port + "/rests"
    url = "{}/data/tapi-common:context"
    return get_request(url)


def delete_tapi_service(ip, port, service_uuid):
    global RESTCONF_BASE_URL
    RESTCONF_BASE_URL = "http://" + ip + ":" + port + "/restconf"
    url = "{}/operations/tapi-connectivity:delete-connectivity-service"
    data = {
        "input": {
            "uuid": service_uuid
        }
    }
    return post_request(url, data)


def tapi_get_services(ip, port):
    global RESTCONF_BASE_URL
    global RESTS_BASE_URL
    RESTCONF_BASE_URL = "http://" + ip + ":" + port + "/restconf"
    RESTS_BASE_URL = "http://" + ip + ":" + port + "/rests"
    url = "{}/operations/tapi-connectivity:get-connectivity-service-list"
    print("------------------GETTING TAPI SERVICES------------------")
    return post_request(url, "")


def mount_tapi_device(node_id, host, port):
    url = URL_CONFIG_NETCONF_TOPO + "node/" + node_id
    body = {"node": [{
        "node-id": node_id,
        "netconf-node-topology:username": NODES_LOGIN,
        "netconf-node-topology:password": NODES_PWD,
        "netconf-node-topology:host": host,
        "netconf-node-topology:port": port,
        "netconf-node-topology:tcp-only": "false",
        "netconf-node-topology:pass-through": {}}]}
    return put_request(url, body)


def connect_xpdr_to_rdm_tapi_request(xpdr_node: str, line_num: str, rdm_node: str, add_num: str):
    url = "{}/operations/transportpce-tapinetworkutils:init-xpdr-rdm-tapi-link"
    data = {
        "input": {
            "xpdr-node": xpdr_node,
            "network-tp": line_num,
            "rdm-node": rdm_node,
            "add-drop-tp": add_num
        }
    }
    return post_request(url, data)


def connect_rdm_to_rdm_tapi_request(rdm_a_node: str, deg_a_num: str, deg_a_dir: str, rdm_z_node: str, deg_z_num: str,
                                    deg_z_dir: str):
    url = "{}/operations/transportpce-tapinetworkutils:nokia-init-roadm-roadm-tapi-link"
    data = {
        "input": {
            "rdm-a-node": rdm_a_node,
            "deg-a-tp": deg_a_num,
            "deg-a-dir": deg_a_dir,
            "rdm-z-node": rdm_z_node,
            "deg-z-tp": deg_z_num,
            "deg-z-dir": deg_z_dir,
            "ots-impairments": {
                "ots-concentrated-loss": {
                    "concentrated-loss": 17.3
                },
                "ots-fiber-span-impairments": {
                    "fiber-type-variety": "smf",
                    "pmd": 1.7,
                    "length": 80,
                    "loss-coef": 0.14,
                    "total-loss": 10,
                    "connector-in": 0.1,
                    "connector-out": 0.1
                }

            }
        }
    }
    return post_request(url, data)


def start_runner():
    def start_loop():
        topology_file = topology_repo.get_contents("inventory.json", ref=MASTER_BRANCH)
        network_inventory = topology_file.decoded_content.decode("utf-8")
        print(network_inventory)
        print("------------------TOPO. JSON FILE------------------")
        network_inventory_json = json.loads(network_inventory)
        node_list = network_inventory_json['topology']['nodes']
        link_list = network_inventory_json['topology']['links']
        vendor_list = []
        for node in node_list:
            if node['vendor'] not in vendor_list and node['type'] == 'ROADM':
                vendor_list.append(node['vendor'])
        if len(vendor_list) > 1:
            recommissioning_fully(node_list, link_list, MINIKUBE_IP, "30181")
        else:
            recommissioning_partially(node_list, link_list, MINIKUBE_IP, "30181")

    print('Started runner')
    thread = Thread(target=start_loop)
    thread.start()


if __name__ == '__main__':
    # start_runner()
    app.run(host=BL_ENGINE_IP, port=BL_ENGINE_PORT, debug=True, use_reloader=True)
