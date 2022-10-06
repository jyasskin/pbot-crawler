from htmlutil import clean_content


def test_drupal():
    assert (
        clean_content(
            rb"""<script type="application/json" data-drupal-selector="drupal-settings-json">{"path":{"baseUrl":"\/","scriptPath":null,"pathPrefix":"","currentPath":"taxonomy\/term\/32","currentPathIsAdmin":false,"isFront":false,"currentLanguage":"en"},"pluralDelimiter":"\u0003","suppressDeprecationErrors":true,"ajaxPageState":{"libraries":"classy\/base,classy\/messages,cloudy\/bootstrap,cloudy\/global,core\/normalize,core\/picturefill,datalayer\/behaviors,extlink\/drupal.extlink,filter\/caption,search_api_autocomplete\/search_api_autocomplete,system\/base,views\/views.ajax,views\/views.module","theme":"cloudy","theme_token":null},"ajaxTrustedUrl":{"\/search":true},"dataLayer":{"defaultLang":"en","languages":{"en":{"id":"en","name":"English","direction":"ltr","weight":0},"es":{"id":"es","name":"Spanish","direction":"ltr","weight":1},"vi":{"id":"vi","name":"Vietnamese","direction":"ltr","weight":2},"zh-hans":{"id":"zh-hans","name":"Chinese, Simplified","direction":"ltr","weight":3},"ru":{"id":"ru","name":"Russian","direction":"ltr","weight":4}}},"data":{"extlink":{"extTarget":false,"extTargetNoOverride":false,"extNofollow":false,"extNoreferrer":false,"extFollowNoOverride":false,"extClass":"ext","extLabel":"(link is external)","extImgClass":false,"extSubdomains":true,"extExclude":"","extInclude":"","extCssExclude":"#toolbar-administration, .field--name-field-facebook, .field--name-field-twitter, .field--name-field-instagram, .field--name-field-youtube, .field--name-field-linkedin, .field--name-field-nextdoor, .cloudy-global-menu, .block-cloudy-main-menu","extCssExplicit":"","extAlert":false,"extAlertText":"This link will take you to an external web site. We are not responsible for their content.","mailtoClass":"0","mailtoLabel":"(link sends email)","extUseFontAwesome":true,"extIconPlacement":"append","extFaLinkClasses":"fas fa-external-link-alt","extFaMailtoClasses":"fa fa-envelope-o","whitelistedDomains":["portland.gov","www.portland.gov","portlandoregon.gov","www.portlandoregon.gov","efiles.portlandoregon.gov","portlandmaps.com","www.portlandmaps.com","www.governmentjobs.com"]}},"field_group":{"html_element":{"mode":"related","context":"view","settings":{"classes":"","id":"","element":"div","show_label":false,"label_element":"h3","label_element_classes":"","attributes":"","effect":"none","speed":"fast"}}},"views":{"ajax_path":"\/views\/ajax","ajaxViews":{"views_dom_id:3339ddacf5dc47431d5ba355d28ace14a62d44a2dc46a952da009fd0558105fb":{"view_name":"taxonomy_content_by_term","view_display_id":"construction_by_term_block","view_args":"32","view_path":"\/taxonomy\/term\/32","view_base_path":"taxonomy\/term\/%\/services","view_dom_id":"3339ddacf5dc47431d5ba355d28ace14a62d44a2dc46a952da009fd0558105fb","pager_element":0}}},"search_api_autocomplete":{"search_portland_gov":{"delay":60,"auto_submit":true,"min_length":3}},"ajax":[],"user":{"uid":0,"permissionsHash":"b5b15b041ddbef12a8224aa503cc2d4718abb37b05b81c6674ad384409c86daf"}}</script>"""
        )
        == rb"""<script type="application/json" data-drupal-selector="drupal-settings-json">{"path":{"baseUrl":"\/","scriptPath":null,"pathPrefix":"","currentPath":"taxonomy\/term\/32","currentPathIsAdmin":false,"isFront":false,"currentLanguage":"en"},"pluralDelimiter":"\u0003","suppressDeprecationErrors":true,"ajaxPageState":{"libraries":"classy\/base,classy\/messages,cloudy\/bootstrap,cloudy\/global,core\/normalize,core\/picturefill,datalayer\/behaviors,extlink\/drupal.extlink,filter\/caption,search_api_autocomplete\/search_api_autocomplete,system\/base,views\/views.ajax,views\/views.module","theme":"cloudy","theme_token":null},"ajaxTrustedUrl":{"\/search":true},"dataLayer":{"defaultLang":"en","languages":{"en":{"id":"en","name":"English","direction":"ltr","weight":0},"es":{"id":"es","name":"Spanish","direction":"ltr","weight":1},"vi":{"id":"vi","name":"Vietnamese","direction":"ltr","weight":2},"zh-hans":{"id":"zh-hans","name":"Chinese, Simplified","direction":"ltr","weight":3},"ru":{"id":"ru","name":"Russian","direction":"ltr","weight":4}}},"data":{"extlink":{"extTarget":false,"extTargetNoOverride":false,"extNofollow":false,"extNoreferrer":false,"extFollowNoOverride":false,"extClass":"ext","extLabel":"(link is external)","extImgClass":false,"extSubdomains":true,"extExclude":"","extInclude":"","extCssExclude":"#toolbar-administration, .field--name-field-facebook, .field--name-field-twitter, .field--name-field-instagram, .field--name-field-youtube, .field--name-field-linkedin, .field--name-field-nextdoor, .cloudy-global-menu, .block-cloudy-main-menu","extCssExplicit":"","extAlert":false,"extAlertText":"This link will take you to an external web site. We are not responsible for their content.","mailtoClass":"0","mailtoLabel":"(link sends email)","extUseFontAwesome":true,"extIconPlacement":"append","extFaLinkClasses":"fas fa-external-link-alt","extFaMailtoClasses":"fa fa-envelope-o","whitelistedDomains":["portland.gov","www.portland.gov","portlandoregon.gov","www.portlandoregon.gov","efiles.portlandoregon.gov","portlandmaps.com","www.portlandmaps.com","www.governmentjobs.com"]}},"field_group":{"html_element":{"mode":"related","context":"view","settings":{"classes":"","id":"","element":"div","show_label":false,"label_element":"h3","label_element_classes":"","attributes":"","effect":"none","speed":"fast"}}},"views":{"ajax_path":"\/views\/ajax","ajaxViews":{"":{"view_name":"taxonomy_content_by_term","view_display_id":"construction_by_term_block","view_args":"32","view_path":"\/taxonomy\/term\/32","view_base_path":"taxonomy\/term\/%\/services","pager_element":0}}},"search_api_autocomplete":{"search_portland_gov":{"delay":60,"auto_submit":true,"min_length":3}},"ajax":[],"user":{"uid":0,"permissionsHash":"b5b15b041ddbef12a8224aa503cc2d4718abb37b05b81c6674ad384409c86daf"}}</script>"""
    )


def test_class():
    assert (
        clean_content(
            rb"""<div><div class="view view-alerts view-id-alerts view-display-id-block_1 js-view-dom-id-7503104ea1e14d980b278a1c110c9c073814c27f5e798af57e6a23495726f168">"""
        )
        == rb"""<div><div class="view view-alerts view-id-alerts view-display-id-block_1 ">"""
    )


def test_nreum():
    assert (
        clean_content(
            rb"""<script type="text/javascript">window.NREUM||(NREUM={});NREUM.info={"beacon":"bam.nr-data.net","licenseKey":"959a8d97de","applicationID":"146857664","transactionName":"YlRaMUNYWhZRUBVaX1seeQZFUFsLH3cTRkBUXWQmXktROXVdFVpETG17Cl9NRgpcXwRBbHBfTAxFQGIMVUQiXF5BQ1cJXVxGSA5FCFZH","queueTime":0,"applicationTime":654,"atts":"ThNZRwtCSRg=","errorBeacon":"bam.nr-data.net","agent":""}</script></body>"""
        )
        == rb"""</body>"""
    )


def test_drawer():
    assert (
        clean_content(
            rb"""<button
    role="button"
    class="drawer__open drawer__open--position-right btn btn-lg"
    data-target=".drawer--1242721986"
    aria-label="Open filters"
    aria-pressed="false"
    aria-expanded="false"
  ><span class="icon icon--size-s"><svg id="icon-filter" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 16 16" width="16" height="16"><title>filter</title><path fill="currentColor" d="M15.5 12H5V11.5C5" /></svg></span><span>Filters</span></button><div
    class="drawer--1242721986 drawer drawer--position-right col-lg-4"
    aria-labelledby="drawer__open"
"""
        )
        == rb"""<button
    role="button"
    class="drawer__open drawer__open--position-right btn btn-lg"
    data-target=".drawer--0000000000"
    aria-label="Open filters"
    aria-pressed="false"
    aria-expanded="false"
  ><span class="icon icon--size-s"><svg id="icon-filter" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" viewBox="0 0 16 16" width="16" height="16"><title>filter</title><path fill="currentColor" d="M15.5 12H5V11.5C5" /></svg></span><span>Filters</span></button><div
    class="drawer--0000000000 drawer drawer--position-right col-lg-4"
    aria-labelledby="drawer__open"
"""
    )


def test_trailing_space():
    assert (
        clean_content(b""" <elem>    \n    \n  text  \n""") == b""" <elem>\n  text\n"""
    )
