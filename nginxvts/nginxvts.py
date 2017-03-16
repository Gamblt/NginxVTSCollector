# coding=utf-8

"""
Collect statistics from Nginx VTS module

#### Dependencies

 * urllib2
 * json

#### Usage

For open source nginx:

    To enable the nginx status page to work with defaults,
    add a file to /etc/nginx/sites-enabled/ (on Ubuntu) with the
    following content:
    <pre>
      server {
            listen 127.0.0.1:80;
            server_name localhost;
            location /status {
                vhost_traffic_status_display;
                vhost_traffic_status_display_format html;
            }
      }
    </pre>
"""
import urllib2
import re
import diamond.collector
import json


class NginxvtsCollector(diamond.collector.Collector):

    def get_default_config_help(self):
        config_help = super(NginxvtsCollector, self).get_default_config_help()
        config_help.update({
            'precision': 'Number of decimal places to report to',
            'req_host': 'Hostname',
            'req_port': 'Port',
            'req_path': 'Path',
            'req_ssl': 'SSL Support',
            'req_host_header': 'HTTP Host header (required for SSL)',
        })
        return config_help

    def get_default_config(self):
        default_config = super(NginxvtsCollector, self).get_default_config()
        default_config['precision'] = 0
        default_config['req_host'] = '127.0.0.1'
        default_config['req_port'] = 80
        default_config['req_path'] = '/status/format/json'
        default_config['req_ssl'] = False
        default_config['req_host_header'] = None
        default_config['path'] = 'nginxvts'
        return default_config

    def collect_nginx_vts(self, status):
        # Collect base info
        hostname = status['hostName']

        # Collect standard stats
        self.collect_connections(hostname, status['connections'])

        # Collect Servers
        if 'serverZones' in status:
            self.collect_server_zones(hostname, status['serverZones'])

        # Collect Upstreams
        if 'upstreamZones' in status:
            self.collect_upstreams(hostname, status['upstreamZones'])

    def collect_connections(self, hostname, status):
        for counter in ['active', 'reading', 'writing', 'waiting', 'handled', 'accepted', 'requests']:
            self.publish_counter('%s.conn.%s' % (hostname, counter), status[counter])

    def collect_server_zones(self, hostname, servers):
        try:
            keys = servers.keys()
            for server in keys:
                name = server
                if (name == '*'):
                    name = 'all'
                prefix = '%s.vhosts.%s' % (hostname, re.sub('[:\./]', '_', name))
                self.publish_counter('%s.requests' % (prefix), servers[server]['requestCounter'])
                self.publish_counter('%s.reqtime' % (prefix), servers[server]['requestMsec'])
                self.publish_counter('%s.sent' % (prefix), servers[server]['outBytes'])
                self.publish_counter('%s.rcvd' % (prefix), servers[server]['inBytes'])

                resp_keys = servers[server]['responses'].keys();
                for counter in resp_keys:
                    self.publish_gauge('%s.responses.%s' % (prefix, counter), servers[server]['responses'][counter])
        except Exception, e:
            self.log.error("Collect server_zones exception: [[%s]]", e)


    def collect_upstreams(self, hostname, upstreams):
        try:
            keys = upstreams.keys()
            for upstream in keys:
                for stream_content in upstreams[upstream]:

                    prefix = '%s.upstreams.%s.%s' % (hostname,
                        re.sub('[:\./]', '_', upstream),
                        re.sub('[:\./]', '_', stream_content['server'])
                    )

                    self.publish_counter('%s.requests' % prefix, stream_content['requestCounter'])
                    self.publish_counter('%s.reqtime' % prefix, stream_content['requestMsec'])
                    self.publish_counter('%s.resptime' % prefix, stream_content['responseMsec'])
                    self.publish_counter('%s.sent' % prefix, stream_content['outBytes'])
                    self.publish_counter('%s.rcvd' % prefix, stream_content['inBytes'])

                    status = '1'
                    if (stream_content['down']):
                        status = '0'

                    self.publish_counter('%s.weight' % prefix, status)

                    resp_keys = stream_content['responses'].keys();
                    for counter in resp_keys:
                        self.publish_gauge('%s.responses.%s' % (prefix, counter), stream_content['responses'][counter])

        except Exception, e:
            self.log.error("Collect upstreams exception: [[%s]]", e)

    #### Main handler
    def collect(self):
        # Determine what HTTP scheme to use based on SSL usage or not
        if str(self.config['req_ssl']).lower() == 'true':
            scheme = 'https'
        else:
            scheme = 'http'

        # Add host headers if present (Required for SSL cert validation)
        if self.config['req_host_header'] is not None:
            headers = {'Host': str(self.config['req_host_header'])}
        else:
            headers = {}

        url = '%s://%s:%i%s' % (scheme,self.config['req_host'],int(self.config['req_port']),self.config['req_path'])

        req = urllib2.Request(url=url, headers=headers)
        try:
            handle = urllib2.urlopen(req)
            self.collect_nginx_vts(json.load(handle))
        except IOError, e:
            self.log.error("1Unable to open [%s]" , url)
        except Exception, e:
            self.log.error("1Unknown error exception: [[%s]]", e)
