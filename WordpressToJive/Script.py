import xml.etree.ElementTree

root = xml.etree.ElementTree.parse('/Users/lschaefer/Downloads/sugardeveloper.wordpress.com-2017-09-11-12_04_39/sugardeveloperblog-sugarcrm.wordpress.2017-09-11.post_type-post.start_date-2017-09-01.end_date-2017-09-30.001.xml').getroot()
# print(root)
# print(root.tag)
# 
# for node in root:
#     print node
#     print node.keys()
#     print node.items()
#     for subnode in node:
#         print subnode
#         print subnode.keys()
#         print subnode.items()

namespaces = {
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'dc': 'http://purl.org/dc/elements/1.1/'
    }

channel = root.find('channel')
for item in channel.findall('item'):
    print item.find('title').text
    print item.find('dc:creator', namespaces).text
    print item.find('content:encoded', namespaces).text